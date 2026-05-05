"""Patch 10 contract tests — title-based DEPT_SLIDE_MAP resolver.

Decision locked 2026-05-04: TITLE-BASED LOOKUP, not hardcoded slide indexes.
Slides may be reordered; only the title contract is stable.
"""
from lib.dept_slide_map import (
    DEPT_TITLE_MAP,
    _extract_slide_title,
    resolve_dept_slide_map,
)


def _slide_with_title(title):
    """Build a Slides API page object with a TITLE placeholder containing `title`."""
    return {
        "pageElements": [
            {
                "shape": {
                    "placeholder": {"type": "TITLE"},
                    "text": {
                        "textElements": [
                            {"textRun": {"content": title}}
                        ]
                    },
                }
            }
        ]
    }


def _slide_without_title():
    return {"pageElements": [{"shape": {}}]}


def test_extract_slide_title_returns_title_text():
    slide = _slide_with_title("Sales · Auto-Updated Scorecard")
    assert _extract_slide_title(slide) == "Sales · Auto-Updated Scorecard"


def test_extract_slide_title_strips_whitespace_and_newlines():
    slide = {
        "pageElements": [
            {
                "shape": {
                    "placeholder": {"type": "TITLE"},
                    "text": {
                        "textElements": [
                            {"textRun": {"content": "Engineering · Auto-Updated Scorecard\n"}}
                        ]
                    },
                }
            }
        ]
    }
    assert _extract_slide_title(slide) == "Engineering · Auto-Updated Scorecard"


def test_extract_slide_title_returns_none_when_no_title_placeholder():
    assert _extract_slide_title(_slide_without_title()) is None


def test_resolve_dept_slide_map_finds_all_nine_depts():
    """Session 3.6 grew the map from 7 → 10 (added bizdev, ai_automations,
    operations). Session 4.1 dropped Leadership per Deuce 2026-05-05 — Leadership
    has no dedicated deck slides; its data still flows into Slack +
    leadership-doc via DEPT_METRIC_ORDER. Net: 9 depts in DEPT_TITLE_MAP."""
    pres = {
        "slides": [
            _slide_with_title("Cover slide"),
            _slide_with_title(DEPT_TITLE_MAP["engineering"]),
            _slide_with_title(DEPT_TITLE_MAP["bizdev"]),
            _slide_with_title(DEPT_TITLE_MAP["supply"]),
            _slide_with_title(DEPT_TITLE_MAP["sales"]),
            _slide_with_title(DEPT_TITLE_MAP["demand_am"]),
            _slide_with_title(DEPT_TITLE_MAP["operations"]),
            _slide_with_title(DEPT_TITLE_MAP["marketing"]),
            _slide_with_title(DEPT_TITLE_MAP["ai_automations"]),
            _slide_with_title(DEPT_TITLE_MAP["accounting"]),
        ]
    }
    result = resolve_dept_slide_map("DECK", fetch_presentation=lambda _id: pres)
    assert set(result.keys()) == set(DEPT_TITLE_MAP.keys())
    assert "leadership" not in result
    assert result["engineering"] == 1
    assert result["accounting"] == 9


def test_resolve_dept_slide_map_handles_missing_dept_slides():
    """Resolver returns only the depts whose titles match — others are
    silently absent and pre-flight surfaces them."""
    pres = {
        "slides": [
            _slide_with_title(DEPT_TITLE_MAP["sales"]),
            _slide_with_title(DEPT_TITLE_MAP["demand_am"]),
            _slide_with_title(DEPT_TITLE_MAP["supply"]),
        ]
    }
    result = resolve_dept_slide_map("DECK", fetch_presentation=lambda _id: pres)
    assert set(result.keys()) == {"sales", "demand_am", "supply"}
    assert "marketing" not in result
    assert "engineering" not in result


def test_resolve_dept_slide_map_picks_first_match_when_titles_duplicate():
    """Per Session 0 PROBE 2: slide 35 is suffixed '(DT V)'. Disambiguation
    is manual prep — but if duplicates ever slip through, the resolver picks
    the first occurrence so behavior is deterministic, not random."""
    pres = {
        "slides": [
            _slide_with_title(DEPT_TITLE_MAP["sales"]),  # canonical at idx 0
            _slide_with_title(DEPT_TITLE_MAP["sales"]),  # duplicate at idx 1
        ]
    }
    result = resolve_dept_slide_map("DECK", fetch_presentation=lambda _id: pres)
    assert result["sales"] == 0


def test_resolve_dept_slide_map_skips_titleless_slides():
    pres = {
        "slides": [
            _slide_without_title(),
            _slide_with_title(DEPT_TITLE_MAP["sales"]),
        ]
    }
    result = resolve_dept_slide_map("DECK", fetch_presentation=lambda _id: pres)
    assert result == {"sales": 1}
