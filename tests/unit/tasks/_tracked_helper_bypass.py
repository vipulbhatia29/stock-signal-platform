"""Test helper: bypass @tracked_task decorator if present, else call directly.

Tests that exercise the private async helpers directly need to work both
BEFORE the Category A/B refactor (decorator not yet applied) and AFTER
(decorator injects run_id and hits real DB). This shim lets the same
test code work through both phases of PR1.5 execution.

Usage:
    from tests.unit.tasks._tracked_helper_bypass import bypass_tracked

    result = await bypass_tracked(_nightly_price_refresh_async)(run_id=uuid.uuid4())
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any


def bypass_tracked(fn: Callable[..., Awaitable[Any]]) -> Callable[..., Awaitable[Any]]:
    """Return the un-decorated helper, stripping run_id if not yet decorated.

    - If ``fn`` has ``.__wrapped__`` (decorator applied): return the inner
      function which accepts ``run_id`` as a kwarg.
    - If ``fn`` has no ``.__wrapped__`` (pre-refactor): return a passthrough
      that strips ``run_id`` from kwargs before forwarding, since the raw
      function doesn't accept it yet.
    """
    wrapped = getattr(fn, "__wrapped__", None)
    if wrapped is not None:
        return wrapped

    # Pre-refactor: strip run_id since the raw function doesn't accept it
    async def _passthrough(*args: Any, **kwargs: Any) -> Any:
        kwargs.pop("run_id", None)
        return await fn(*args, **kwargs)

    return _passthrough
