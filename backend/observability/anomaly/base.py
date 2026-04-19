"""Base types for the anomaly detection engine."""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import UUID


@dataclass(frozen=True, slots=True)
class Finding:
    """Structured output from an anomaly rule evaluation."""

    kind: str
    attribution_layer: str
    severity: str
    title: str
    evidence: dict
    dedup_key: str
    remediation_hint: str | None = None
    related_traces: list[UUID] = field(default_factory=list)
    suggested_jira_fields: dict | None = None
    opened_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class AnomalyRule(abc.ABC):
    """Contract for anomaly detection rules."""

    @property
    @abc.abstractmethod
    def name(self) -> str:
        """Unique rule identifier."""

    @abc.abstractmethod
    async def evaluate(self) -> list[Finding]:
        """Run the rule and return any findings."""
