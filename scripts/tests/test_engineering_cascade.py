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


def test_w1_live_handlers_bridged_into_engineering_live_metrics():
    """F-1 fix: every key in metric_payloads._LIVE_HANDLERS must be registered
    in ENGINEERING_LIVE_METRICS so render_one_row's Step 0a fires for them
    before Step 0b's needs_build placeholder. If this regresses, the 3 W.1
    hero metrics (Features Fully Scoped / PRDs Generated / FSDs Generated)
    will surface as '🔨 (Phase 2 migration)' on Slack/deck/leadership-doc
    instead of their live BQ values.
    """
    from lib.metric_payloads import _LIVE_HANDLERS

    # Non-empty guard — protects against future regression where someone
    # empties _LIVE_HANDLERS and the subset assertion below trivially passes.
    assert len(_LIVE_HANDLERS) >= 3, (
        f"_LIVE_HANDLERS has {len(_LIVE_HANDLERS)} entries, expected ≥3 (W.1 trio). "
        f"Did someone remove the W.1 handlers from metric_payloads.py?"
    )
    assert set(_LIVE_HANDLERS.keys()) <= set(ENGINEERING_LIVE_METRICS.keys()), (
        f"_LIVE_HANDLERS has keys not bridged into ENGINEERING_LIVE_METRICS: "
        f"{set(_LIVE_HANDLERS.keys()) - set(ENGINEERING_LIVE_METRICS.keys())}. "
        f"Update scorecard_renderer.py's ENGINEERING_LIVE_METRICS comprehension."
    )
    # The 3 W.1 metrics MUST be registered. Pin by name so a future rename
    # in _LIVE_HANDLERS or dashboard registry fails this test loudly.
    for w1_metric in ("Features Fully Scoped", "PRDs Generated", "FSDs Generated"):
        assert w1_metric in ENGINEERING_LIVE_METRICS, (
            f"{w1_metric!r} missing from ENGINEERING_LIVE_METRICS — F-1 regressed."
        )


def test_w1_dispatch_renders_live_value_not_phase2_placeholder():
    """End-to-end F-1 verification: with a fresh adapter wrapped around a fake
    handler returning 9, render_one_row for the real 'Features Fully Scoped'
    metric name (registered in dashboard as needs_build) routes through Step 0a
    and produces a live display value '9', NOT the Phase 2 placeholder.

    Patches ENGINEERING_LIVE_METRICS directly with a freshly-built adapter —
    `_adapt_live_handler` captures handler refs at construction time via
    closure, so the indirection through `_PAYLOAD_LIVE_HANDLERS` isn't useful
    in tests (mutating the dict post-load doesn't reach the existing closures).
    """
    # `"format": "number"` matches the real dashboard registry entry for
    # the W.1 metrics. `"count"` is not a registered format and would diverge
    # at value≥1000 (str(1500)='1500' vs _format_metric_value=>='1,500').
    entry = {
        "name": "Features Fully Scoped",
        "key": "Features Fully Scoped",
        "scorecard_status": "needs_build",
        "format": "number",
        "icon": "🎯",
        "icon_class": "cyan",
        "bq_key": None,
    }

    with patch.dict(
        ENGINEERING_LIVE_METRICS,
        {"Features Fully Scoped": scorecard_renderer._adapt_live_handler(lambda: 9)},
    ), patch(
        "lib.scorecard_renderer.get_scorecard_dept_sensitivity",
        return_value="public",
    ):
        row = render_one_row(entry, "engineering", {}, date(2026, 5, 10))

    assert row.display == "9", (
        f"Expected display='9', got {row.display!r}. F-1 fix broken — "
        f"Step 0a should win over Step 0b for needs_build entries that "
        f"have a live handler."
    )
    assert row.is_phase2_placeholder is False
    assert row.actual_raw == 9
