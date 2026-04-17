"""Observability target adapters — the extraction seam."""

from backend.observability.targets.base import BatchResult, ObservabilityTarget, TargetHealth
from backend.observability.targets.memory import MemoryTarget

__all__ = ["BatchResult", "MemoryTarget", "ObservabilityTarget", "TargetHealth"]
