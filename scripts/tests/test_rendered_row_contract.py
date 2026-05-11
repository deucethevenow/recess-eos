"""Patch 1 contract tests — RenderedRow + render_one_row.

The contract: every metric flows through render_one_row and produces a
RenderedRow whose `display` field is the canonical value-and-target string
consumed identically by deck, Slack, and leadership-doc writers.

Test fixtures use `key` not `name` — get_scorecard_metrics_for_dept returns
entries shaped as {**registry_value, "key": registry_dict_key}, so the canonical
identifier in production is `key`. The C1 review finding caught a bug where
test fixtures used `"name"` and masked the production crash.
"""
from datetime import date
from unittest.mock import patch

import pytest

from lib.rendered_row import RenderedRow
from lib.scorecard_renderer import (
    PHASE2_PLACEHOLDER,
    SPECIAL_METRIC_NAMES,
    render_one_row,
)


# ----- RenderedRow shape ---------------------------------------------------- #


def test_rendered_row_has_all_contract_fields():
    """Session 3.7: RenderedRow now includes actual_display + target_display
    so the deck writer can split the combined display string into the deck's
    per-column layout (col 1 Target, col 2 Actual). The single `display`
    field stays in place for Slack/leadership-doc which still consume the
    combined form."""
    row = RenderedRow(
        metric_name="X",
        display_label="X (Per Dept)",
        dept_id="leadership",
        sensitivity="public",
        actual_raw=1.0,
        target_raw=2.0,
        status_icon="🟢",
        display="$1 / $2 (50%)  ·  target $2",
        actual_display="$1 / $2 (50%)",
        target_display="$2",
        trend_display=None,
        is_phase2_placeholder=False,
        is_special_override=False,
    )
    assert row.metric_name == "X"
    assert row.display_label == "X (Per Dept)"
    assert row.display == "$1 / $2 (50%)  ·  target $2"
    assert row.actual_display == "$1 / $2 (50%)"
    assert row.target_display == "$2"
    assert row.trend_display is None
    assert row.is_phase2_placeholder is False
    assert row.is_special_override is False


# ----- Cascade Step 0a: needs_build → Phase 2 placeholder ------------------- #


def test_needs_build_returns_phase2_placeholder_with_flag():
    entry = {
        "key": "Some Phase 2 Metric",
        "scorecard_status": "needs_build",
    }
    with patch(
        "lib.scorecard_renderer.get_scorecard_dept_sensitivity",
        return_value="public",
    ), patch(
        "lib.scorecard_renderer.get_scorecard_label",
        side_effect=lambda e, d, n: n,
    ):
        row = render_one_row(entry, "engineering", {}, date(2026, 5, 5))
    assert row.display == PHASE2_PLACEHOLDER
    assert row.is_phase2_placeholder is True
    assert row.status_icon == "\U0001F528"


def test_phase2_placeholder_display_is_identical_for_all_writers():
    """Same row, same display string — what deck, Slack, leadership doc all see."""
    entry = {"key": "Y", "scorecard_status": "needs_build"}
    with patch(
        "lib.scorecard_renderer.get_scorecard_dept_sensitivity",
        return_value="public",
    ), patch(
        "lib.scorecard_renderer.get_scorecard_label",
        side_effect=lambda e, d, n: n,
    ):
        row = render_one_row(entry, "engineering", {}, date(2026, 5, 5))
    deck_cell_text = row.display
    slack_line = f"• *{row.display_label}*: {row.display}"
    leadership_text = row.display
    assert PHASE2_PLACEHOLDER in deck_cell_text
    assert PHASE2_PLACEHOLDER in slack_line
    assert PHASE2_PLACEHOLDER in leadership_text


# ----- Cascade Step 0b: asana_goal status (C2 fix) ------------------------- #


def test_asana_goal_status_calls_render_asana_goal_not_live_metric():
    """C2 regression test: asana_goal status MUST call _render_asana_goal,
    NOT fall through to _render_live_metric (which would return the
    'Batch 3 will wire' placeholder for entries with bq_key=None)."""
    entry = {"key": "Some Asana Goal", "scorecard_status": "asana_goal"}
    with patch(
        "lib.scorecard_renderer._render_asana_goal",
        return_value="✅ 75% (Asana Goal)",
    ) as mock_asana, patch(
        "lib.scorecard_renderer._render_live_metric",
    ) as mock_live, patch(
        "lib.scorecard_renderer.get_scorecard_dept_sensitivity",
        return_value="public",
    ), patch(
        "lib.scorecard_renderer.get_scorecard_label",
        side_effect=lambda e, d, n: n,
    ), patch(
        "lib.scorecard_renderer._fmt_target",
        return_value=None,
    ):
        row = render_one_row(entry, "leadership", {}, date(2026, 5, 5))
    mock_asana.assert_called_once_with(entry)
    mock_live.assert_not_called()
    assert "✅ 75%" in row.display


# ----- I1: STATIC_SCORECARD_TARGETS fallback in target cascade ------------- #


def test_target_cascade_falls_back_to_static_scorecard_targets(monkeypatch):
    """When _fmt_target returns None (no registry-side scorecard_target), the
    cascade falls back to STATIC_SCORECARD_TARGETS. Without this wiring (I1
    review finding), the dict is dead code."""
    entry = {"key": "Days to First Offer", "format": "days"}
    monkeypatch.setattr("lib.scorecard_renderer._fmt_target", lambda e, d: None)
    monkeypatch.setattr(
        "lib.scorecard_renderer._render_live_metric",
        lambda e, d, cm, n: "12 days",
    )
    with patch(
        "lib.scorecard_renderer.get_scorecard_dept_sensitivity",
        return_value="public",
    ), patch(
        "lib.scorecard_renderer.get_scorecard_label",
        side_effect=lambda e, d, n: n,
    ):
        row = render_one_row(entry, "sales", {}, date(2026, 5, 5))
    assert "target" in row.display
    assert "30" in row.display


# ----- Special override surface --------------------------------------------- #


def test_special_metric_names_set_includes_three_known_overrides():
    assert SPECIAL_METRIC_NAMES == {
        "Demand NRR",
        "Pipeline Coverage",
        "Bill Payment Timeliness",
    }


# ----- Sensitivity passthrough ---------------------------------------------- #


@pytest.mark.parametrize(
    "registered_sens,expected", [("public", "public"), ("leadership", "leadership"), ("founders_only", "founders_only")]
)
def test_render_one_row_passes_through_registry_sensitivity(registered_sens, expected):
    entry = {"key": "Test", "scorecard_status": "needs_build"}
    with patch(
        "lib.scorecard_renderer.get_scorecard_dept_sensitivity",
        return_value=registered_sens,
    ), patch(
        "lib.scorecard_renderer.get_scorecard_label",
        side_effect=lambda e, d, n: n,
    ):
        row = render_one_row(entry, "leadership", {}, date(2026, 5, 5))
    assert row.sensitivity == expected


# ----- C1 regression: real registry entries don't crash render_one_row ----- #


def test_render_one_row_does_not_crash_on_real_registry_entries():
    """The C1 review finding: production entries from get_scorecard_metrics_for_dept
    have `key` (not `name`). Hand-fabricated test fixtures masked this bug.
    This integration-style test exercises render_one_row against the real
    registry to catch any future regressions of the same kind."""
    from dashboard.data.metric_registry import get_scorecard_metrics_for_dept  # type: ignore
    from dashboard.data.data_layer import _get_empty_company_metrics  # type: ignore

    entries = get_scorecard_metrics_for_dept("leadership")
    if not entries:
        pytest.skip("registry has no leadership scorecard entries — nothing to render")

    company_metrics = _get_empty_company_metrics()
    today = date(2026, 5, 5)
    for entry in entries:
        # Should not raise — every registry entry must produce a RenderedRow.
        row = render_one_row(entry, "leadership", company_metrics, today)
        assert row.metric_name, f"render_one_row produced empty metric_name for entry {entry.get('key')}"
        assert row.display, f"render_one_row produced empty display for {entry.get('key')}"
        assert row.display_label, f"render_one_row produced empty display_label for {entry.get('key')}"
