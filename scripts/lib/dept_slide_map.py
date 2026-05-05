"""Title-based DEPT_SLIDE_MAP resolver for /monday-kpi-update.

Per v3.8 Patch 10 (closes B20). Decision locked 2026-05-04 (Deuce): use TITLE-BASED
LOOKUP, not fixed slide-index renumber. Rationale: drift-resilient against future
deck reorganizations — when slides are moved or new ones inserted, the slash command
keeps working with no code change.

Two parallel maps as of Session 4:
  DEPT_TITLE_MAP       — scorecard slides ("<Dept> · Auto-Updated Scorecard")
  DEPT_ROCKS_TITLE_MAP — rocks/projects slides ("<Dept> · Auto-Updated Rocks & Projects")

Both maps share the same dept_id keys but with different title suffixes. The
resolver is generic via `_resolve_slide_map_for_titles(deck_id, title_map, ...)`
so the same code handles both maps without duplication.

Slide 34/35 disambiguation (legacy Sales duplicates noted in PROBE 2): manual
prep BEFORE first run picks one canonical and renames or deletes the other.
Title-based resolver auto-picks whichever has the EXACT target title.
"""
from typing import Any, Callable, Dict, List, Optional

DEPT_TITLE_MAP: Dict[str, str] = {
    "sales": "Sales · Auto-Updated Scorecard",
    "demand_am": "Account Management · Auto-Updated Scorecard",
    "supply": "Supply · Auto-Updated Scorecard",
    "bizdev": "BizDev · Auto-Updated Scorecard",
    "marketing": "Marketing · Auto-Updated Scorecard",
    "ai_automations": "AI Automations · Auto-Updated Scorecard",
    "operations": "Operations · Auto-Updated Scorecard",
    "engineering": "Engineering · Auto-Updated Scorecard",
    "accounting": "Accounting · Auto-Updated Scorecard",
}
# 9 depts have deck slides (Leadership intentionally excluded per Deuce
# 2026-05-05). The resolver returns {dept_id: slide_idx} for each dept whose
# title is found; pre-flight fails loud for any dept in DEPT_TITLE_MAP whose
# slide is missing (manual prep error). Depts NOT in DEPT_TITLE_MAP — like
# Leadership — are silently skipped by the deck writer; their data still flows
# into Slack and leadership-doc surfaces (those use DEPT_METRIC_ORDER, not
# this map).


DEPT_ROCKS_TITLE_MAP: Dict[str, str] = {
    dept_id: title.replace("Auto-Updated Scorecard", "Auto-Updated Rocks & Projects")
    for dept_id, title in DEPT_TITLE_MAP.items()
}
# Same dept_ids as DEPT_TITLE_MAP, with the "Scorecard" → "Rocks & Projects"
# title suffix. Each dept slide pair is rendered in lock-step: scorecard +
# rocks/projects. Manual-prep adds 10 slides matching this title pattern.


def _extract_slide_titles(slide: Dict[str, Any]) -> List[str]:
    """Return ALL non-empty text strings on a slide.

    Slides API returns each slide with `pageElements[]`. Title text may live
    in a TITLE placeholder OR in a regular text-box shape (the all-hands deck
    uses plain text boxes for the scorecard slide titles, so the placeholder
    type is empty rather than "TITLE"). We accept any shape with text content.

    The caller (`resolve_dept_slide_map`) decides which strings constitute a
    title by matching against the expected dept title strings. This is more
    robust than filtering by placeholder type — the deck owner can use any
    shape style (text box, title placeholder, group element) as long as the
    string matches exactly.
    """
    out: List[str] = []
    for elem in slide.get("pageElements", []) or []:
        shape = elem.get("shape") or {}
        text = shape.get("text") or {}
        runs: List[str] = []
        for te in text.get("textElements", []) or []:
            tr = te.get("textRun") or {}
            content = tr.get("content")
            if content:
                runs.append(content)
        joined = "".join(runs).strip()
        if joined:
            out.append(joined)
    return out


def _extract_slide_title(slide: Dict[str, Any]) -> Optional[str]:
    """Return the FIRST non-empty text string on a slide.

    Kept for backward compatibility with tests that fixture a single-shape
    slide. New code should call `_extract_slide_titles` (plural) and match
    against the expected title set.
    """
    titles = _extract_slide_titles(slide)
    return titles[0] if titles else None


def _resolve_slide_map_for_titles(
    deck_id: str,
    title_map: Dict[str, str],
    slides_service=None,
    fetch_presentation: Optional[Callable[[str], Dict[str, Any]]] = None,
) -> Dict[str, int]:
    """Generic resolver — match `title_map` keys to slide indexes by title.

    Used by both `resolve_dept_slide_map` (scorecard) and
    `resolve_dept_rocks_slide_map` (rocks/projects). Either `slides_service`
    (Google API client) or `fetch_presentation` (callable returning the parsed
    presentation dict) may be supplied for testability. If both are None,
    raises ValueError.
    """
    if fetch_presentation is not None:
        pres = fetch_presentation(deck_id)
    elif slides_service is not None:
        pres = slides_service.presentations().get(presentationId=deck_id).execute()
    else:
        raise ValueError(
            "_resolve_slide_map_for_titles requires slides_service or fetch_presentation"
        )

    slides = pres.get("slides", []) or []
    title_to_idx: Dict[str, int] = {}
    for idx, slide in enumerate(slides):
        for title in _extract_slide_titles(slide):
            title_to_idx.setdefault(title, idx)

    return {
        dept_id: title_to_idx[expected_title]
        for dept_id, expected_title in title_map.items()
        if expected_title in title_to_idx
    }


def resolve_dept_slide_map(
    deck_id: str,
    slides_service=None,
    fetch_presentation: Optional[Callable[[str], Dict[str, Any]]] = None,
) -> Dict[str, int]:
    """Find each dept's SCORECARD slide by exact title match.

    Returns {dept_id: slide_index} for every dept whose scorecard slide title
    is found. Depts with no matching slide are simply absent from the result —
    the pre-flight in Patch 5 surfaces them loudly so manual prep is
    unambiguous.
    """
    return _resolve_slide_map_for_titles(
        deck_id, DEPT_TITLE_MAP, slides_service, fetch_presentation
    )


def resolve_dept_rocks_slide_map(
    deck_id: str,
    slides_service=None,
    fetch_presentation: Optional[Callable[[str], Dict[str, Any]]] = None,
) -> Dict[str, int]:
    """Find each dept's ROCKS & PROJECTS slide by exact title match.

    Symmetric with resolve_dept_slide_map but uses DEPT_ROCKS_TITLE_MAP.
    """
    return _resolve_slide_map_for_titles(
        deck_id, DEPT_ROCKS_TITLE_MAP, slides_service, fetch_presentation
    )
