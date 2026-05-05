"""Patch 8 contract tests — cascade order (live wins over phase2).

The contract: in render_one_row, Step 0a (ENGINEERING_LIVE_METRICS check)
MUST appear in source BEFORE Step 0b (needs_build → Phase 2 placeholder).

If swapped, all engineering live metrics regress to '🔨 (Phase 2 migration)' —
the exact bug v3.6 was created to prevent.
"""
import inspect
from datetime import date
from unittest.mock import patch

from lib import scorecard_renderer
from lib.scorecard_renderer import (
    ENGINEERING_LIVE_METRICS,
    PHASE2_PLACEHOLDER,
    render_one_row,
)


def test_cascade_step_0a_precedes_step_0b_at_source_level():
    """Source-level invariant: the ENGINEERING_LIVE_METRICS check appears
    before the Phase 2 placeholder return. This catches a code reviewer
    re-ordering the cascade by accident."""
    src = inspect.getsource(render_one_row)
    a_idx = src.find("ENGINEERING_LIVE_METRICS")
    b_idx = src.find("(Phase 2 migration)")
    assert a_idx > 0, "ENGINEERING_LIVE_METRICS check missing from render_one_row"
    assert b_idx > 0, "Phase 2 migration placeholder missing from render_one_row"
    assert a_idx < b_idx, (
        "Cascade order regression: ENGINEERING_LIVE_METRICS check moved AFTER "
        "the Phase 2 placeholder return. Step 0a must precede Step 0b."
    )


def test_engineering_live_metric_renders_via_live_function_not_phase2():
    """Behavioral counterpart to the source-level test. If a metric is in
    ENGINEERING_LIVE_METRICS AND has scorecard_status='needs_build', the
    live function wins — it does not regress to the Phase 2 placeholder."""
    entry = {"name": "Test Live", "scorecard_status": "needs_build"}

    def live_fn(entry, dept_id, company_metrics):
        return (1.0, "live value")

    with patch.dict(ENGINEERING_LIVE_METRICS, {"Test Live": live_fn}):
        with patch(
            "lib.scorecard_renderer.get_scorecard_dept_sensitivity",
            return_value="public",
        ):
            row = render_one_row(entry, "engineering", {}, date(2026, 5, 5))
    assert row.display == "live value"
    assert row.display != PHASE2_PLACEHOLDER
    assert row.is_phase2_placeholder is False


def test_phase2_placeholder_text_is_stable():
    """If the placeholder text changes, all 3 surface writers see it. Don't
    silently let a typo or unicode swap drift the contract — pin the bytes."""
    assert scorecard_renderer.PHASE2_PLACEHOLDER == "\U0001F528 (Phase 2 migration)"
