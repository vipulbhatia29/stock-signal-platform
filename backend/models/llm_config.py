"""LLM model cascade configuration."""

from datetime import datetime

from sqlalchemy import Boolean, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.models.base import Base


class LLMModelConfig(Base):
    """Configurable LLM model cascade — one row per model per tier."""

    __tablename__ = "llm_model_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    provider: Mapped[str] = mapped_column(String(20), nullable=False)
    model_name: Mapped[str] = mapped_column(String(100), nullable=False)
    tier: Mapped[str] = mapped_column(String(20), nullable=False)
    priority: Mapped[int] = mapped_column(Integer, nullable=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    tpm_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rpm_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tpd_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rpd_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cost_per_1k_input: Mapped[float] = mapped_column(Numeric(10, 6), default=0)
    cost_per_1k_output: Mapped[float] = mapped_column(Numeric(10, 6), default=0)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )
