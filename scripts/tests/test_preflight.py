"""Patch 5 contract tests — pre-flight runtime checks.

Pre-flight runs BEFORE the sensitivity gate. Any failure aborts the run and
posts to #kpi-dashboard-notifications. Three checks:
  1. Rocks data freshness  (rocks.available must be True)
  2. Deck table row counts (>= 1 + N + 2 per dept)
  3. Today is logged       (audit trail)
"""
from datetime import date

import pytest

from lib import preflight as pf
from lib.preflight import PreflightError, run_preflight
from lib.rendered_row import RenderedRow


def _row(name="X"):
    return RenderedRow(
        metric_name=name,
        display_label=name,
        dept_id="leadership",
        sensitivity="public",
        actual_raw=None,
        target_raw=None,
        status_icon="⚪",
        display="$1",
        actual_display="$1",
        target_display=None,
        trend_display=None,
        is_phase2_placeholder=False,
        is_special_override=False,
    )


def _disable_alert(monkeypatch):
    """Suppress the network call so tests don't try to POST to Slack."""
    monkeypatch.setattr(pf, "emit_failure_alert", lambda **kw: None)


def test_preflight_fails_when_rocks_unavailable(monkeypatch):
    _disable_alert(monkeypatch)
    with pytest.raises(PreflightError, match="Rock data unavailable"):
        run_preflight(
            today=date(2026, 5, 5),
            company_metrics={},
            rock_data={"available": False},
            rendered_per_dept={},
            deck_id="DECK",
            fetch_table_row_count=lambda d, s: 99,
        )


def test_preflight_fails_when_table_row_underflow(monkeypatch):
    _disable_alert(monkeypatch)
    rendered = {
        "sales": {
            "scorecard_rows": [_row(f"M{i}") for i in range(12)],
            "slide_idx": 28,
        }
    }
    # 12 metrics → required = 1 + 12 + 2 = 15 rows. Provide 9.
    with pytest.raises(PreflightError) as exc:
        run_preflight(
            today=date(2026, 5, 5),
            company_metrics={},
            rock_data={"available": True},
            rendered_per_dept=rendered,
            deck_id="DECK",
            fetch_table_row_count=lambda d, s: 9,
        )
    msg = str(exc.value)
    assert "sales" in msg
    assert "9" in msg
    assert "15" in msg


def test_preflight_fails_when_slide_has_no_table(monkeypatch):
    _disable_alert(monkeypatch)
    rendered = {
        "sales": {"scorecard_rows": [_row()], "slide_idx": 28}
    }
    with pytest.raises(PreflightError, match="has NO table"):
        run_preflight(
            today=date(2026, 5, 5),
            company_metrics={},
            rock_data={"available": True},
            rendered_per_dept=rendered,
            deck_id="DECK",
            fetch_table_row_count=lambda d, s: None,
        )


def test_preflight_flags_dept_with_no_resolved_slide_idx(monkeypatch):
    """If resolve_dept_slide_map didn't find a matching slide title, slide_idx
    is None on the payload. Pre-flight surfaces this loudly so manual prep
    knows exactly which dept needs a slide created."""
    _disable_alert(monkeypatch)
    rendered = {
        "marketing": {"scorecard_rows": [_row()], "slide_idx": None}
    }
    with pytest.raises(PreflightError, match="no slide_idx resolved"):
        run_preflight(
            today=date(2026, 5, 5),
            company_metrics={},
            rock_data={"available": True},
            rendered_per_dept=rendered,
            deck_id="DECK",
            fetch_table_row_count=lambda d, s: 100,
        )


def test_preflight_logs_pinned_today_only_on_success(capsys, monkeypatch):
    _disable_alert(monkeypatch)
    run_preflight(
        today=date(2026, 5, 5),
        company_metrics={},
        rock_data={"available": True},
        rendered_per_dept={},
        deck_id="DECK",
        fetch_table_row_count=lambda d, s: 100,
    )
    out = capsys.readouterr().out
    # I3 fix: success message says PASS (not OK) and includes the pinned date.
    assert "Pre-flight PASS" in out
    assert "today=2026-05-05" in out


def test_preflight_does_not_log_pass_when_failures_present(capsys, monkeypatch):
    """I3 fix: do NOT print 'PASS' before raising on failures. An operator
    scanning logs after the run should see ONLY failure context, not a
    misleading 'PASS' line."""
    _disable_alert(monkeypatch)
    with pytest.raises(PreflightError):
        run_preflight(
            today=date(2026, 5, 5),
            company_metrics={},
            rock_data={"available": False},
            rendered_per_dept={},
            deck_id="DECK",
            fetch_table_row_count=lambda d, s: 100,
        )
    out = capsys.readouterr().out
    assert "Pre-flight PASS" not in out


def test_preflight_fails_loud_when_fetch_table_row_count_is_none_but_slides_resolved(monkeypatch):
    """C4 fix: silently skipping the deck-row check when fetch_table_row_count
    is None defeats the entire Patch 5 contract. If any dept has a resolved
    slide_idx, the row-count fetcher is required."""
    _disable_alert(monkeypatch)
    rendered = {
        "sales": {"scorecard_rows": [_row()], "slide_idx": 28}
    }
    with pytest.raises(PreflightError, match="fetch_table_row_count is None"):
        run_preflight(
            today=date(2026, 5, 5),
            company_metrics={},
            rock_data={"available": True},
            rendered_per_dept=rendered,
            deck_id="DECK",
            fetch_table_row_count=None,
        )


def test_preflight_allows_skip_when_no_slides_resolved_and_fetcher_is_none(monkeypatch):
    """If NO dept has a resolved slide_idx (e.g., --skip-deck mode where
    DEPT_SLIDE_MAP is intentionally empty), it's fine to omit the fetcher."""
    _disable_alert(monkeypatch)
    rendered = {
        "sales": {"scorecard_rows": [_row()], "slide_idx": None}
    }
    # The single failure here is the 'no slide_idx resolved' message,
    # NOT the 'fetch_table_row_count is None' message.
    with pytest.raises(PreflightError, match="no slide_idx resolved") as exc:
        run_preflight(
            today=date(2026, 5, 5),
            company_metrics={},
            rock_data={"available": True},
            rendered_per_dept=rendered,
            deck_id="DECK",
            fetch_table_row_count=None,
        )
    assert "fetch_table_row_count is None" not in str(exc.value)


def test_preflight_passes_when_all_conditions_met(monkeypatch):
    _disable_alert(monkeypatch)
    rendered = {
        "sales": {
            "scorecard_rows": [_row(f"M{i}") for i in range(5)],
            "slide_idx": 28,
        }
    }
    # 5 metrics → required = 1 + 5 + 2 = 8 rows. Provide 10. Should pass.
    run_preflight(
        today=date(2026, 5, 5),
        company_metrics={},
        rock_data={"available": True},
        rendered_per_dept=rendered,
        deck_id="DECK",
        fetch_table_row_count=lambda d, s: 10,
    )
