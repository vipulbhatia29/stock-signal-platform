"""Request/response schemas for LLM model config admin API."""

from pydantic import BaseModel


class LLMModelConfigResponse(BaseModel):
    """Response schema for a single LLM model config row."""

    id: int
    provider: str
    model_name: str
    tier: str
    priority: int
    is_enabled: bool
    tpm_limit: int | None
    rpm_limit: int | None
    tpd_limit: int | None
    rpd_limit: int | None
    cost_per_1k_input: float
    cost_per_1k_output: float
    notes: str | None

    model_config = {"from_attributes": True}


class LLMModelConfigUpdate(BaseModel):
    """Partial update schema — only provided fields are applied."""

    priority: int | None = None
    is_enabled: bool | None = None
    tpm_limit: int | None = None
    rpm_limit: int | None = None
    tpd_limit: int | None = None
    rpd_limit: int | None = None
    cost_per_1k_input: float | None = None
    cost_per_1k_output: float | None = None
    notes: str | None = None
