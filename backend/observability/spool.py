"""Append-only JSONL spool — survives target outages without blocking emit().

- One file per worker (spool-{pid}.jsonl)
- Per-worker byte cap; overflow = drop (oldest-first rotation is OUT of scope)
- No-op when OBS_SPOOL_ENABLED=false (constructor short-circuits upstream)
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import AsyncIterator

import aiofiles

from backend.observability.schema.v1 import ObsEventBase


@dataclass(frozen=True)
class AppendResult:
    """Result of appending events to the spool file."""

    written: int
    dropped: int


class SpoolWriter:
    """Appends events as JSONL to a per-worker spool file."""

    def __init__(self, directory: Path, max_size_mb: int) -> None:
        self._dir = Path(directory)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._max_bytes = max_size_mb * 1024 * 1024
        self._file = self._dir / f"spool-{os.getpid()}.jsonl"

    async def append(self, events: list[ObsEventBase]) -> AppendResult:
        """Append events to the spool file, respecting size cap."""
        current = self._file.stat().st_size if self._file.exists() else 0
        if current >= self._max_bytes:
            return AppendResult(written=0, dropped=len(events))
        written = 0
        dropped = 0
        async with aiofiles.open(self._file, mode="a") as fh:
            for ev in events:
                line = ev.model_dump_json() + "\n"
                line_bytes = len(line.encode())
                if current + line_bytes > self._max_bytes:
                    dropped += 1
                    continue
                await fh.write(line)
                current += line_bytes
                written += 1
        return AppendResult(written=written, dropped=dropped)


class SpoolReader:
    """Drains spool files by reading and deleting them."""

    def __init__(self, directory: Path) -> None:
        self._dir = Path(directory)

    async def drain(self) -> AsyncIterator[ObsEventBase]:
        """Yield events from all spool files, deleting each after reading."""
        for path in sorted(self._dir.glob("spool-*.jsonl")):
            async with aiofiles.open(path, mode="r") as fh:
                async for raw in fh:
                    raw = raw.strip()
                    if not raw:
                        continue
                    yield ObsEventBase.model_validate_json(raw)
            path.unlink(missing_ok=True)
