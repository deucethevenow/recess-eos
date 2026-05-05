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


def test_resolve_dept_slide_map_finds_all_seven_depts():
    pres = {
        "slides": [
            _slide_with_title("Cover slide"),
            _slide_with_title(DEPT_TITLE_MAP["leadership"]),
            _slide_with_title(DEPT_TITLE_MAP["sales"]),
            _slide_with_title(DEPT_TITLE_MAP["demand_am"]),
            _slide_with_title(DEPT_TITLE_MAP["supply"]),
            _slide_with_title(DEPT_TITLE_MAP["marketing"]),
            _slide_with_title(DEPT_TITLE_MAP["engineering"]),
            _slide_with_title(DEPT_TITLE_MAP["accounting"]),
        ]
    }
    result = resolve_dept_slide_map("DECK", fetch_presentation=lambda _id: pres)
    assert set(result.keys()) == set(DEPT_TITLE_MAP.keys())
    assert result["leadership"] == 1
    assert result["sales"] == 2
    assert result["accounting"] == 7


def test_resolve_dept_slide_map_handles_missing_dept_slides():
    """Per Session 0 PROBE 2: only 3 of 7 dept slides exist today. The
    resolver returns just those that match — pre-flight then surfaces the
    missing ones."""
    pres = {
        "slides": [
            _slide_with_title(DEPT_TITLE_MAP["leadership"]),
            _slide_with_title(DEPT_TITLE_MAP["sales"]),
            _slide_with_title(DEPT_TITLE_MAP["demand_am"]),
        ]
    }
    result = resolve_dept_slide_map("DECK", fetch_presentation=lambda _id: pres)
    assert set(result.keys()) == {"leadership", "sales", "demand_am"}
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
            _slide_with_title(DEPT_TITLE_MAP["leadership"]),
        ]
    }
    result = resolve_dept_slide_map("DECK", fetch_presentation=lambda _id: pres)
    assert result == {"leadership": 1}
