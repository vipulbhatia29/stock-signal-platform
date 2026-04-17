"""Observability target adapters — the extraction seam."""

from backend.observability.targets.base import BatchResult, ObservabilityTarget, TargetHealth
from backend.observability.targets.direct import DirectTarget
from backend.observability.targets.internal_http import InternalHTTPTarget
from backend.observability.targets.memory import MemoryTarget

__all__ = [
    "BatchResult",
    "DirectTarget",
    "InternalHTTPTarget",
    "MemoryTarget",
    "ObservabilityTarget",
    "TargetHealth",
]
