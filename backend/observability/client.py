"""ObservabilityClient — single emission abstraction (spec §2.1).

Loop-safety contract:
- emit() (async) + emit_sync() (sync) both funnel through buffer.try_put
- Buffer is loop-agnostic queue.Queue so calls from ANY loop work
- _flush_loop runs on start()'s loop; drains buffer via asyncio.to_thread
- stop() signals _stopping first, awaits flush task cleanly, then final drain

Hard-rule semantics:
- emit/emit_sync NEVER raise (swallow all exceptions, log + drop-or-spool)
- _flush_loop wrapped in top-level try/except to survive poison events
- enabled=False -> both emit paths are no-ops; no background tasks started
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path

from backend.observability.buffer import EventBuffer
from backend.observability.schema.v1 import ObsEventBase
from backend.observability.spool import SpoolReader, SpoolWriter
from backend.observability.targets.base import ObservabilityTarget

logger = logging.getLogger(__name__)


@dataclass
class ClientHealth:
    """Health snapshot of the observability client."""

    enabled: bool
    queue_depth: int
    drops: int
    target_healthy: bool
    last_target_error: str | None


class ObservabilityClient:
    """Buffered async/sync emission client with optional disk spool."""

    def __init__(
        self,
        *,
        target: ObservabilityTarget,
        spool_dir: Path,
        spool_enabled: bool,
        flush_interval_ms: int,
        buffer_size: int,
        enabled: bool,
        max_batch: int = 500,
        spool_max_size_mb: int = 100,
        reclaim_interval_s: float = 30.0,
    ) -> None:
        self._target = target
        self._enabled = enabled
        self._buffer = EventBuffer(buffer_size)
        self._spool_enabled = spool_enabled
        self._spool_writer = SpoolWriter(spool_dir, spool_max_size_mb) if spool_enabled else None
        self._spool_reader = SpoolReader(spool_dir) if spool_enabled else None
        self._flush_interval = flush_interval_ms / 1000.0
        self._max_batch = max_batch
        self._reclaim_interval = reclaim_interval_s
        self._flush_task: asyncio.Task[None] | None = None
        self._reclaim_task: asyncio.Task[None] | None = None
        self._stopping = asyncio.Event()

    async def start(self) -> None:
        """Start background flush + reclaim tasks."""
        if not self._enabled:
            return
        self._flush_task = asyncio.create_task(self._flush_loop())
        if self._spool_enabled:
            self._reclaim_task = asyncio.create_task(self._reclaim_loop())

    async def stop(self) -> None:
        """Signal stop FIRST, let the flush loop exit naturally, then final drain.

        Fixes the double-drainer race: previous version awaited flush() before
        cancelling the flush task, which meant two coroutines contended on the
        same queue.
        """
        if not self._enabled:
            return
        self._stopping.set()
        if self._flush_task:
            try:
                await asyncio.wait_for(self._flush_task, timeout=5.0)
            except asyncio.TimeoutError:
                self._flush_task.cancel()
        if self._reclaim_task:
            self._reclaim_task.cancel()
        # Final sync drain to catch anything still queued at shutdown.
        await self._drain_once(block=False)

    async def emit(self, event: ObsEventBase) -> None:
        """Async non-blocking emit — safe from FastAPI request handlers."""
        if not self._enabled:
            return
        self._enqueue_or_overflow(event, is_async=True)

    def emit_sync(self, event: ObsEventBase) -> None:
        """Sync non-blocking emit — safe from yfinance/requests/rate-limiter sync paths.

        Does NOT create asyncio tasks (caller may not be on an event loop). Uses the
        same buffer as async emit; spool overflow drops-and-warns in sync context
        rather than awaiting aiofiles.
        """
        if not self._enabled:
            return
        self._enqueue_or_overflow(event, is_async=False)

    def _enqueue_or_overflow(self, event: ObsEventBase, *, is_async: bool) -> None:
        """Try to enqueue; on overflow, spool (async) or drop (sync)."""
        try:
            if self._buffer.try_put(event):
                return
        except Exception:  # noqa: BLE001 — must not propagate
            logger.warning("obs.emit.try_put_raised", exc_info=True)
            return
        # Overflow path.
        if not self._spool_writer:
            logger.warning(
                "obs.event_dropped.buffer_overflow",
                extra={"event_type": event.event_type.value},
            )
            return
        if is_async:
            # Fire-and-forget: schedule spool write on the caller's loop.
            try:
                asyncio.get_running_loop().create_task(self._spool_writer.append([event]))
            except RuntimeError:
                # Not on a running loop — fall back to drop.
                logger.warning(
                    "obs.event_dropped.sync_context_no_loop",
                    extra={"event_type": event.event_type.value},
                )
        else:
            # Sync context — drop with warn (no loop to await aiofiles on).
            logger.warning(
                "obs.event_dropped.sync_overflow",
                extra={"event_type": event.event_type.value},
            )

    async def flush(self, timeout_s: float = 5.0) -> None:
        """Drain buffer once — used in tests and shutdown."""
        if not self._enabled:
            return
        await self._drain_once(block=True, timeout_s=timeout_s)

    async def _drain_once(self, *, block: bool, timeout_s: float = 1.0) -> None:
        """Pull a batch from the buffer and send to target."""
        timeout = timeout_s if block else 0.0
        batch = await asyncio.to_thread(self._buffer.get_batch, self._max_batch, timeout)
        if batch:
            await self._send(batch)

    async def health(self) -> ClientHealth:
        """Report client health including buffer stats and target state."""
        stats = self._buffer.stats()
        target_health = await self._target.health()
        return ClientHealth(
            enabled=self._enabled,
            queue_depth=stats.depth,
            drops=stats.drops,
            target_healthy=target_health.healthy,
            last_target_error=target_health.last_error,
        )

    async def _flush_loop(self) -> None:
        """Top-level try/except prevents a single poison event from killing the flusher."""
        while not self._stopping.is_set():
            try:
                batch = await asyncio.to_thread(
                    self._buffer.get_batch, self._max_batch, self._flush_interval
                )
                if batch:
                    await self._send(batch)
            except Exception:  # noqa: BLE001 — survive poison events
                logger.exception("obs.flush_loop.iteration_failed")
                await asyncio.sleep(0.1)  # back off briefly

    async def _send(self, batch: list[ObsEventBase]) -> None:
        """Send batch to target; spool on failure if enabled."""
        try:
            result = await self._target.send_batch(batch)
            if result.failed > 0 and self._spool_writer:
                await self._spool_writer.append(batch)
        except Exception:  # noqa: BLE001 — target errors must not propagate past _send
            logger.warning("obs.target.send_raised", exc_info=True)
            if self._spool_writer:
                try:
                    await self._spool_writer.append(batch)
                except Exception:
                    logger.warning("obs.spool.append_after_send_failed", exc_info=True)

    async def _reclaim_loop(self) -> None:
        """Periodically replay spooled events to the target."""
        assert self._spool_reader is not None
        while not self._stopping.is_set():
            await asyncio.sleep(self._reclaim_interval)
            try:
                batch: list[ObsEventBase] = []
                async for ev in self._spool_reader.drain():
                    batch.append(ev)
                    if len(batch) >= self._max_batch:
                        await self._send(batch)
                        batch = []
                if batch:
                    await self._send(batch)
            except Exception:  # noqa: BLE001
                logger.exception("obs.reclaim.iteration_failed")
