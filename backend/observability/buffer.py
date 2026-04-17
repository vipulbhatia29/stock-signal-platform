"""Loop-agnostic bounded event buffer for the observability SDK.

Uses stdlib queue.Queue(maxsize=N): thread-safe, loop-agnostic, AND enforces
a hard bound via put_nowait -> queue.Full on overflow. Survives Celery's
per-task asyncio.run() pattern (fresh loop per task) because queue.Queue has
no loop binding, unlike asyncio.Queue.
"""

from __future__ import annotations

import queue
from dataclasses import dataclass

from backend.observability.schema.v1 import ObsEventBase


@dataclass
class BufferStats:
    """Snapshot of buffer state."""

    depth: int
    drops: int


class EventBuffer:
    """Loop-agnostic bounded queue — safe from any thread + any event loop.

    Survives Celery's per-task asyncio.run() pattern (fresh loop per task)
    because queue.Queue has no loop binding, unlike asyncio.Queue.
    """

    def __init__(self, max_size: int) -> None:
        self._queue: queue.Queue[ObsEventBase] = queue.Queue(maxsize=max_size)
        self._drops = 0

    def try_put(self, event: ObsEventBase) -> bool:
        """Non-blocking enqueue. Returns False + increments drop counter on overflow."""
        try:
            self._queue.put_nowait(event)
            return True
        except queue.Full:
            self._drops += 1
            return False

    def get_batch(self, max_batch: int, timeout_s: float) -> list[ObsEventBase]:
        """Block up to timeout_s for the first event, then drain non-blockingly.

        Call from a worker thread via asyncio.to_thread so it never blocks a loop.
        """
        try:
            first = self._queue.get(timeout=timeout_s)
        except queue.Empty:
            return []
        batch = [first]
        while len(batch) < max_batch:
            try:
                batch.append(self._queue.get_nowait())
            except queue.Empty:
                break
        return batch

    def stats(self) -> BufferStats:
        """Return current queue depth and cumulative drop count."""
        return BufferStats(depth=self._queue.qsize(), drops=self._drops)
