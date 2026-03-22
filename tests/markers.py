"""Custom pytest markers for test gating."""
import pytest

pre_commit = pytest.mark.pre_commit
ci_only = pytest.mark.ci_only
agent_gated = pytest.mark.agent_gated
