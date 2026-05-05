"""Session 4 contract tests — rocks/projects deck slide writer.

Covers:
  1. DEPT_ROCKS_TITLE_MAP is populated for all 10 depts with the
     "<Dept> · Auto-Updated Rocks & Projects" suffix.
  2. resolve_dept_rocks_slide_map finds rocks slides by title.
  3. render_rock_or_project_row produces the expected 5-col fields
     (Metric / Target / Actual / Status / Trend).
  4. Status thresholds (66% green, 33% yellow, <33% red).
  5. Preflight fails loud on missing rocks slides when skip_rocks_deck=False.
"""
from datetime import date

import pytest

from lib.dept_slide_map import (
    DEPT_ROCKS_TITLE_MAP,
    DEPT_TITLE_MAP,
    resolve_dept_rocks_slide_map,
)
from lib.preflight import PreflightError, run_preflight
from lib.rendered_row import RenderedRow
from lib.scorecard_renderer import render_rock_or_project_row


# ----- DEPT_ROCKS_TITLE_MAP shape ----------------------------------------- #


def test_rocks_title_map_covers_same_depts_as_scorecard_map():
    """Each scorecard dept should have a matching rocks slide entry."""
    assert set(DEPT_ROCKS_TITLE_MAP.keys()) == set(DEPT_TITLE_MAP.keys())


def test_rocks_title_map_titles_use_correct_suffix():
    for dept_id, title in DEPT_ROCKS_TITLE_MAP.items():
        assert title.endswith(" · Auto-Updated Rocks & Projects")
        # Stripping the suffix should yield a dept label
        prefix = title.removesuffix(" · Auto-Updated Rocks & Projects")
        assert prefix  # non-empty


# ----- Title resolver ------------------------------------------------------ #


def _slide_with_title(title):
    return {
        "pageElements": [
            {
                "shape": {
                    "text": {
                        "textElements": [{"textRun": {"content": title}}]
                    }
                }
            }
        ]
    }


def test_resolve_rocks_finds_all_ten_depts():
    pres = {
        "slides": [
            _slide_with_title("Cover slide"),
            _slide_with_title(DEPT_ROCKS_TITLE_MAP["leadership"]),
            _slide_with_title(DEPT_ROCKS_TITLE_MAP["sales"]),
            _slide_with_title(DEPT_ROCKS_TITLE_MAP["demand_am"]),
            _slide_with_title(DEPT_ROCKS_TITLE_MAP["supply"]),
            _slide_with_title(DEPT_ROCKS_TITLE_MAP["bizdev"]),
            _slide_with_title(DEPT_ROCKS_TITLE_MAP["marketing"]),
            _slide_with_title(DEPT_ROCKS_TITLE_MAP["ai_automations"]),
            _slide_with_title(DEPT_ROCKS_TITLE_MAP["operations"]),
            _slide_with_title(DEPT_ROCKS_TITLE_MAP["engineering"]),
            _slide_with_title(DEPT_ROCKS_TITLE_MAP["accounting"]),
        ]
    }
    result = resolve_dept_rocks_slide_map(
        "DECK", fetch_presentation=lambda _id: pres
    )
    assert set(result.keys()) == set(DEPT_ROCKS_TITLE_MAP.keys())


def test_resolve_rocks_omits_depts_with_no_slide():
    pres = {
        "slides": [
            _slide_with_title(DEPT_ROCKS_TITLE_MAP["leadership"]),
        ]
    }
    result = resolve_dept_rocks_slide_map(
        "DECK", fetch_presentation=lambda _id: pres
    )
    assert result == {"leadership": 0}


def test_resolve_rocks_distinct_from_scorecard():
    """Scorecard and rocks slides on the same deck must NOT cross-resolve.
    Each map matches only its own title suffix."""
    pres = {
        "slides": [
            _slide_with_title(DEPT_TITLE_MAP["sales"]),  # scorecard
            _slide_with_title(DEPT_ROCKS_TITLE_MAP["sales"]),  # rocks
        ]
    }
    rocks_map = resolve_dept_rocks_slide_map(
        "DECK", fetch_presentation=lambda _id: pres
    )
    # Rocks map should only match the rocks title (idx 1), not scorecard (idx 0)
    assert rocks_map["sales"] == 1


# ----- render_rock_or_project_row ----------------------------------------- #


def test_render_rock_high_completion_returns_green():
    row = render_rock_or_project_row(
        {"name": "Rock A", "owner_name": "Deuce", "completion_percent": 80, "task_count": 50},
        "leadership",
    )
    assert row.display_label == "Rock A"
    assert row.target_display == "100%"
    assert row.actual_display == "80% (50 tasks)"
    assert "🟢" in row.status_icon
    assert "On-track" in row.status_icon
    assert row.trend_display == "Owner: Deuce"
    assert row.target_raw == 100.0
    assert row.actual_raw == 80.0


def test_render_rock_trend_display_populates_with_owner():
    """Session 4 IMPORTANT fix: trend_display now flows through to deck col 4
    (Trend) — was previously computed but discarded."""
    row = render_rock_or_project_row(
        {"name": "Rock", "owner_name": "Charlene", "completion_percent": 50},
        "demand_am",
    )
    assert row.trend_display == "Owner: Charlene"


def test_render_rock_trend_display_falls_back_to_unassigned():
    row = render_rock_or_project_row(
        {"name": "Orphan", "completion_percent": 25},
        "leadership",
    )
    assert row.trend_display == "Owner: Unassigned"


def test_render_rock_mid_completion_returns_yellow():
    row = render_rock_or_project_row(
        {"name": "Rock B", "owner_name": "Char", "completion_percent": 50, "task_count": 20},
        "demand_am",
    )
    assert "🟡" in row.status_icon
    assert "At-risk" in row.status_icon


def test_render_rock_low_completion_returns_red():
    row = render_rock_or_project_row(
        {"name": "Rock C", "owner_name": "Ines", "completion_percent": 15, "task_count": 86},
        "operations",
    )
    assert "🔴" in row.status_icon
    assert "Off-track" in row.status_icon
    assert row.actual_display == "15% (86 tasks)"


def test_render_rock_omits_task_count_when_missing():
    row = render_rock_or_project_row(
        {"name": "Project Sans Tasks", "owner_name": "Andres", "completion_percent": 47},
        "demand_am",
    )
    assert row.actual_display == "47%"


def test_render_rock_owner_appears_in_combined_display_for_slack():
    """Slack/leadership-doc still consume the combined `display` field —
    cron's _format_rock_line equivalent. Verify it includes name + pct + owner."""
    row = render_rock_or_project_row(
        {"name": "Test Rock", "owner_name": "TestOwner", "completion_percent": 75},
        "leadership",
    )
    assert "Test Rock" in row.display
    assert "75%" in row.display
    assert "TestOwner" in row.display


def test_render_rock_unassigned_owner_falls_back_to_label():
    row = render_rock_or_project_row(
        {"name": "Orphan Rock", "completion_percent": 0},
        "leadership",
    )
    assert "Unassigned" in row.display
    # status icon should be red since pct=0
    assert "🔴" in row.status_icon


def test_render_rock_sensitivity_default_is_leadership():
    """Rocks/projects are not appropriate for public-channel default —
    deck audience IS leadership-tier so this is the right scope."""
    row = render_rock_or_project_row(
        {"name": "X", "completion_percent": 50},
        "leadership",
    )
    assert row.sensitivity == "leadership"


# ----- Preflight rocks check ---------------------------------------------- #


def _scorecard_dept(slide_idx, n_rows=3):
    rows = [
        RenderedRow(
            metric_name=f"M{i}",
            display_label=f"M{i}",
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
        for i in range(n_rows)
    ]
    return {"scorecard_rows": rows, "slide_idx": slide_idx}


def test_preflight_fails_when_rocks_slide_missing(monkeypatch):
    """If skip_rocks_deck=False AND a dept has rocks data but no rocks
    slide, preflight should fail loud — same architectural pattern as
    scorecard slides."""
    from lib import preflight as pf
    monkeypatch.setattr(pf, "emit_failure_alert", lambda **kw: None)

    rendered_per_dept = {"leadership": _scorecard_dept(slide_idx=39)}
    rendered_rocks_per_dept = {
        "leadership": {
            "scorecard_rows": [
                render_rock_or_project_row(
                    {"name": "R", "completion_percent": 50}, "leadership"
                )
            ],
            "slide_idx": None,  # missing rocks slide
        }
    }

    with pytest.raises(PreflightError, match="rocks slide_idx"):
        run_preflight(
            today=date(2026, 5, 5),
            company_metrics={},
            rock_data={"available": True, "rocks": [], "projects": []},
            rendered_per_dept=rendered_per_dept,
            deck_id="DECK",
            fetch_table_row_count=lambda d, s: 99,
            rendered_rocks_per_dept=rendered_rocks_per_dept,
            skip_rocks_deck=False,
        )


def test_preflight_skips_rocks_check_when_skip_rocks_deck_true(monkeypatch):
    from lib import preflight as pf
    monkeypatch.setattr(pf, "emit_failure_alert", lambda **kw: None)

    rendered_per_dept = {"leadership": _scorecard_dept(slide_idx=39)}
    rendered_rocks_per_dept = {
        "leadership": {
            "scorecard_rows": [
                render_rock_or_project_row(
                    {"name": "R", "completion_percent": 50}, "leadership"
                )
            ],
            "slide_idx": None,
        }
    }

    # Should NOT raise — skip_rocks_deck=True bypasses rocks slide check.
    run_preflight(
        today=date(2026, 5, 5),
        company_metrics={},
        rock_data={"available": True, "rocks": [], "projects": []},
        rendered_per_dept=rendered_per_dept,
        deck_id="DECK",
        fetch_table_row_count=lambda d, s: 99,
        rendered_rocks_per_dept=rendered_rocks_per_dept,
        skip_rocks_deck=True,
    )


def test_preflight_skips_rocks_check_when_no_rocks_data(monkeypatch):
    from lib import preflight as pf
    monkeypatch.setattr(pf, "emit_failure_alert", lambda **kw: None)

    rendered_per_dept = {"leadership": _scorecard_dept(slide_idx=39)}

    # No rendered_rocks_per_dept passed — preflight skips rocks checks.
    run_preflight(
        today=date(2026, 5, 5),
        company_metrics={},
        rock_data={"available": True, "rocks": [], "projects": []},
        rendered_per_dept=rendered_per_dept,
        deck_id="DECK",
        fetch_table_row_count=lambda d, s: 99,
        # rendered_rocks_per_dept omitted (default None)
    )
