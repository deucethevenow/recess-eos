"""Day-1 contract tests — rich_metric_renderer.

Covers:
  1. 4-state status comparator (Off-track Q / Off-track A / At-risk / On-track)
       — priority order is critical: Off-track Q wins over Off-track A
       — None inputs handled gracefully (some metrics have no target)
  2. _ratio_from_pacing converts compute_pacing's `pct` (delta/expected)
       into actual/expected ratio.
  3. Format helpers (_short_currency, _full_currency, _pct).
  4. SALES_METRIC_SPECS shape — Net Revenue YTD + alias entries are valid.
  5. render_rich_sales_metric returns None for unconfigured metrics
     (caller falls back to simpler renderer).
  6. render_rich_sales_metric returns a RichMetricPayload when configured.

Note: agent dispatch already validated the dashboard's compute_pacing,
get_team_quota, and compute_coverage are pure Python functions — these
tests focus on the THIN ADAPTER logic in this module.
"""
from datetime import date
from unittest.mock import patch

import pytest

from lib.rich_metric_renderer import (
    AT_RISK_THRESHOLD,
    OFF_TRACK_THRESHOLD,
    SALES_METRIC_SPECS,
    RichMetricPayload,
    _full_currency,
    _pct,
    _ratio_from_pacing,
    _resolve_quarter_label,
    _short_currency,
    compute_4_state_status,
    render_rich_sales_metric,
)


# ----- _ratio_from_pacing -------------------------------------------------- #


def test_ratio_from_pacing_on_pace_returns_one():
    """When delta=0 (perfectly on pace), pct=0, ratio=1.0."""
    pacing = {"pct": 0.0}
    assert _ratio_from_pacing(pacing) == 1.0


def test_ratio_from_pacing_behind_returns_below_one():
    """delta=-50% of expected → pct=-0.5 → ratio=0.5 (50% of pace)."""
    pacing = {"pct": -0.5}
    assert _ratio_from_pacing(pacing) == 0.5


def test_ratio_from_pacing_ahead_returns_above_one():
    """delta=+25% of expected → pct=0.25 → ratio=1.25 (25% ahead)."""
    pacing = {"pct": 0.25}
    assert _ratio_from_pacing(pacing) == 1.25


def test_ratio_from_pacing_returns_none_when_pct_missing():
    assert _ratio_from_pacing({"pct": None}) is None
    assert _ratio_from_pacing({}) is None


def test_ratio_from_pacing_returns_none_when_pacing_is_none():
    assert _ratio_from_pacing(None) is None


# ----- compute_4_state_status — priority order ----------------------------- #


def _pacing_at_ratio(ratio: float) -> dict:
    """Build a fake compute_pacing dict where actual/expected = ratio."""
    return {"pct": ratio - 1.0}  # invert _ratio_from_pacing


def test_status_off_track_q_wins_over_off_track_a():
    """When BOTH quarter and annual are critically behind, the more
    time-urgent state (Off-track Q) is reported. Q-end is sooner than
    Y-end so it's the higher-priority alert."""
    icon, label = compute_4_state_status(
        q_pacing=_pacing_at_ratio(0.5),  # critically behind quarter
        annual_pacing=_pacing_at_ratio(0.5),  # critically behind annual
    )
    assert label == "Off-track Q"
    assert "🔴" in icon


def test_status_off_track_a_when_quarter_ok_but_annual_critical():
    icon, label = compute_4_state_status(
        q_pacing=_pacing_at_ratio(1.05),  # ahead of quarter pace
        annual_pacing=_pacing_at_ratio(0.5),  # critically behind annual
    )
    assert label == "Off-track A"
    assert "🔴" in icon


def test_status_at_risk_when_quarter_in_band():
    """At-risk band: 85% ≤ ratio < 100%."""
    icon, label = compute_4_state_status(
        q_pacing=_pacing_at_ratio(0.92),
        annual_pacing=_pacing_at_ratio(1.05),
    )
    assert label == "At-risk"
    assert "🟡" in icon


def test_status_at_risk_when_annual_in_band():
    icon, label = compute_4_state_status(
        q_pacing=_pacing_at_ratio(1.10),
        annual_pacing=_pacing_at_ratio(0.92),
    )
    assert label == "At-risk"


def test_status_on_track_when_both_meet_or_exceed():
    icon, label = compute_4_state_status(
        q_pacing=_pacing_at_ratio(1.10),
        annual_pacing=_pacing_at_ratio(1.05),
    )
    assert label == "On-track"
    assert "🟢" in icon


def test_status_on_track_with_only_quarter_pacing():
    """Some metrics have only Q pacing (no annual). On-track if Q is met."""
    icon, label = compute_4_state_status(
        q_pacing=_pacing_at_ratio(1.05),
        annual_pacing=None,
    )
    assert label == "On-track"


def test_status_on_track_with_only_annual_pacing():
    icon, label = compute_4_state_status(
        q_pacing=None,
        annual_pacing=_pacing_at_ratio(1.05),
    )
    assert label == "On-track"


def test_status_on_track_when_both_pacings_none():
    """Defensive: no data → on-track (caller decides whether to render)."""
    icon, label = compute_4_state_status(q_pacing=None, annual_pacing=None)
    assert label == "On-track"


def test_status_threshold_exact_boundaries():
    """At ratio=0.85 exactly: not off-track (off-track is STRICTLY <0.85).
    At ratio=1.0 exactly: not at-risk (at-risk is STRICTLY <1.0)."""
    # ratio = OFF_TRACK_THRESHOLD exactly → at-risk, NOT off-track
    icon, label = compute_4_state_status(
        q_pacing=_pacing_at_ratio(OFF_TRACK_THRESHOLD),
        annual_pacing=_pacing_at_ratio(1.0),
    )
    assert label == "At-risk"

    # ratio = AT_RISK_THRESHOLD exactly → on-track, NOT at-risk
    icon, label = compute_4_state_status(
        q_pacing=_pacing_at_ratio(AT_RISK_THRESHOLD),
        annual_pacing=_pacing_at_ratio(1.0),
    )
    assert label == "On-track"


# ----- Format helpers ----------------------------------------------------- #


def test_short_currency_handles_millions():
    assert _short_currency(1_234_567) == "$1.23M"
    assert _short_currency(2_000_000) == "$2M"  # trims .00


def test_short_currency_handles_thousands():
    assert _short_currency(817_000) == "$817K"
    assert _short_currency(36_000) == "$36K"


def test_short_currency_handles_negative():
    assert _short_currency(-609_000) == "-$609K"
    assert _short_currency(-1_220_000) == "-$1.22M"


def test_short_currency_handles_zero_and_none():
    assert _short_currency(0) == "$0"
    assert _short_currency(None) == "—"


def test_full_currency_uses_full_precision():
    assert _full_currency(2_817_036) == "$2,817,036"
    assert _full_currency(10_768_144) == "$10,768,144"


def test_full_currency_handles_none():
    assert _full_currency(None) == "—"


def test_pct_basic():
    assert _pct(227, 2817) == "8%"
    assert _pct(2590, 10768) == "24%"


def test_pct_handles_zero_denom():
    assert _pct(100, 0) == "—"


def test_pct_handles_none():
    assert _pct(None, 100) == "—"
    assert _pct(100, None) == "—"


# ----- _resolve_quarter_label -------------------------------------------- #


def test_resolve_quarter_label_q1():
    assert _resolve_quarter_label(date(2026, 1, 15)) == "Q1"
    assert _resolve_quarter_label(date(2026, 3, 31)) == "Q1"


def test_resolve_quarter_label_q2():
    assert _resolve_quarter_label(date(2026, 4, 1)) == "Q2"
    assert _resolve_quarter_label(date(2026, 5, 8)) == "Q2"
    assert _resolve_quarter_label(date(2026, 6, 30)) == "Q2"


def test_resolve_quarter_label_q3_q4():
    assert _resolve_quarter_label(date(2026, 7, 15)) == "Q3"
    assert _resolve_quarter_label(date(2026, 12, 31)) == "Q4"


# ----- SALES_METRIC_SPECS shape ------------------------------------------ #


def test_net_revenue_ytd_spec_present():
    """Net Revenue YTD is the day-1 reference implementation."""
    assert "Net Revenue YTD" in SALES_METRIC_SPECS
    spec = SALES_METRIC_SPECS["Net Revenue YTD"]
    assert spec.actual_q_key == "demand_nrr_q_revenue"
    assert spec.actual_ytd_key == "revenue_actual"
    assert spec.target_q_source == "firestore_team_net_revenue_quota"


# ----- render_rich_sales_metric ------------------------------------------ #


def test_render_returns_none_for_unconfigured_metric():
    """Falls back to simpler renderer when metric isn't in SALES_METRIC_SPECS."""
    result = render_rich_sales_metric(
        metric_key="Some Random Metric",
        dept_id="sales",
        company_metrics={},
        today=date(2026, 5, 8),
    )
    assert result is None


def test_render_net_revenue_ytd_with_fixture_data():
    """Verify the full pipeline: actuals + Firestore target → 4-column payload.

    Uses fake company_metrics + monkeypatches get_team_quota so the test
    doesn't hit Firestore.
    """
    fake_metrics = {
        "demand_nrr_q_revenue": 67_265,  # Q2 actual ≈ dashboard $67K
        "revenue_actual": 1_059_834,  # YTD actual ≈ dashboard $1.06M
        "revenue_target": 5_521_390,  # annual target
    }
    with patch(
        "lib.rich_metric_renderer.get_team_quota",
        return_value={"team_net_revenue_quota": 1_380_348, "team_bookings_quota": 2_817_036},
    ):
        result = render_rich_sales_metric(
            metric_key="Net Revenue YTD",
            dept_id="sales",
            company_metrics=fake_metrics,
            today=date(2026, 5, 8),
        )

    assert result is not None
    assert isinstance(result, RichMetricPayload)
    # Target column shows Q2 + Annual
    assert "Q2: $1,380,348" in result.target_display
    assert "Annual: $5,521,390" in result.target_display
    # Actual column shows Q + YTD with percentages
    assert "Q: $67K" in result.actual_display
    assert "YTD: $1.06M" in result.actual_display
    # Status shows colored icon + 4-state label (off-track expected since
    # actuals are well below pace).
    assert "🔴" in result.status_icon or "🟡" in result.status_icon
    # Trend has Q Pace + Gap
    assert "Pace" in result.trend_display
    assert "Gap" in result.trend_display


def test_render_handles_missing_actual_gracefully():
    """If company_metrics doesn't have the actual_q_key, render still
    produces a payload with em-dashes for missing fields."""
    fake_metrics = {}
    with patch(
        "lib.rich_metric_renderer.get_team_quota",
        return_value={"team_net_revenue_quota": 1_380_348},
    ):
        result = render_rich_sales_metric(
            metric_key="Net Revenue YTD",
            dept_id="sales",
            company_metrics=fake_metrics,
            today=date(2026, 5, 8),
        )

    assert result is not None
    # Status: defensive — None pacings → on-track (no data to flag against)
    assert "🟢" in result.status_icon


def test_render_handles_firestore_unavailable():
    """If Firestore raises, target_q is None — still produces a payload
    (with target column showing only annual or em-dash)."""
    fake_metrics = {
        "demand_nrr_q_revenue": 67_265,
        "revenue_actual": 1_059_834,
        "revenue_target": 5_521_390,
    }
    with patch(
        "lib.rich_metric_renderer.get_team_quota",
        side_effect=RuntimeError("Firestore unavailable"),
    ):
        result = render_rich_sales_metric(
            metric_key="Net Revenue YTD",
            dept_id="sales",
            company_metrics=fake_metrics,
            today=date(2026, 5, 8),
        )

    assert result is not None
    # Annual target still resolves from company_metrics — should appear.
    assert "Annual: $5,521,390" in result.target_display
    # Q target is missing — Q2 portion of target_display should NOT appear.
    assert "Q2: " not in result.target_display
