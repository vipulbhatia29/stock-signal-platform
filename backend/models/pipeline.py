"""Pipeline observability models — watermark tracking and run logs."""

from datetime import date, datetime

from sqlalchemy import Date, DateTime, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from backend.models.base import Base, UUIDPrimaryKeyMixin


class PipelineWatermark(Base):
    """Tracks pipeline progress for gap detection and recovery."""

    __tablename__ = "pipeline_watermarks"

    pipeline_name: Mapped[str] = mapped_column(String(50), primary_key=True)
    last_completed_date: Mapped[date] = mapped_column(Date, nullable=False)
    last_completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ok")

    def __repr__(self) -> str:
        return (
            f"<PipelineWatermark {self.pipeline_name} {self.last_completed_date} ({self.status})>"
        )


class PipelineRun(UUIDPrimaryKeyMixin, Base):
    """Observability log for every pipeline execution."""

    __tablename__ = "pipeline_runs"

    pipeline_name: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="running")
    tickers_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tickers_succeeded: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tickers_failed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_summary: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    trigger: Mapped[str] = mapped_column(String(20), nullable=False, default="scheduled")

    def __repr__(self) -> str:
        return (
            f"<PipelineRun {self.pipeline_name} {self.status} "
            f"({self.tickers_succeeded}/{self.tickers_total})>"
        )
