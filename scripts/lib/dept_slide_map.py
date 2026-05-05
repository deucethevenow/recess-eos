"""Title-based DEPT_SLIDE_MAP resolver for /monday-kpi-update.

Per v3.8 Patch 10 (closes B20). Decision locked 2026-05-04 (Deuce): use TITLE-BASED
LOOKUP, not fixed slide-index renumber. Rationale: drift-resilient against future
deck reorganizations — when slides are moved or new ones inserted, the slash command
keeps working with no code change.

Expected slide titles (case + spacing must match exactly):
  "Leadership · Auto-Updated Scorecard"
  "Sales · Auto-Updated Scorecard"
  "Account Management · Auto-Updated Scorecard"
  "Supply · Auto-Updated Scorecard"
  "Marketing · Auto-Updated Scorecard"
  "Engineering · Auto-Updated Scorecard"
  "Accounting · Auto-Updated Scorecard"

Per Session 0 PROBE 2: only 3 of 7 dept slides exist today. The resolver returns
just the slides that match — pre-flight (Patch 5) then surfaces missing ones loudly.

Slide 34/35 disambiguation (Sales has duplicates today; PROBE 2 noted slide 35 is
"(DT V)"-suffixed): manual prep BEFORE first run picks one canonical and renames
or deletes the other. Title-based resolver auto-picks whichever has the EXACT
target title.
"""
from typing import Any, Callable, Dict, List, Optional

DEPT_TITLE_MAP: Dict[str, str] = {
    "leadership": "Leadership · Auto-Updated Scorecard",
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
# All 10 depts have deck slides as of 2026-05-05. The resolver returns
# {dept_id: slide_idx} for each dept whose title is found; pre-flight fails
# loud for any dept in DEPT_TITLE_MAP whose slide is missing (manual prep
# error). Depts NOT in DEPT_TITLE_MAP would be silently skipped — the
# preflight optional-slide pattern is preserved for future flexibility (e.g.,
# adding a dept that's only in Slack but not on the deck).


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


def resolve_dept_slide_map(
    deck_id: str,
    slides_service=None,
    fetch_presentation: Optional[Callable[[str], Dict[str, Any]]] = None,
) -> Dict[str, int]:
    """Find each dept's scorecard slide by exact title match.

    Returns {dept_id: slide_index} for every dept whose title is found. Depts
    with no matching slide are simply absent from the result — the pre-flight
    in Patch 5 surfaces them loudly so manual prep is unambiguous.

    Either `slides_service` (Google API client) or `fetch_presentation`
    (callable returning the parsed presentation dict) may be supplied for
    testability. If both are None, raises ValueError.
    """
    if fetch_presentation is not None:
        pres = fetch_presentation(deck_id)
    elif slides_service is not None:
        pres = slides_service.presentations().get(presentationId=deck_id).execute()
    else:
        raise ValueError(
            "resolve_dept_slide_map requires slides_service or fetch_presentation"
        )

    slides = pres.get("slides", []) or []
    # Build title → first-occurrence-idx by walking ALL text on every slide.
    # A slide can carry multiple text shapes; setdefault preserves the FIRST
    # match so duplicate titles (e.g., the legacy slides 34/35 with the same
    # "Sales" title) resolve to the canonical first instance.
    title_to_idx: Dict[str, int] = {}
    for idx, slide in enumerate(slides):
        for title in _extract_slide_titles(slide):
            title_to_idx.setdefault(title, idx)

    return {
        dept_id: title_to_idx[expected_title]
        for dept_id, expected_title in DEPT_TITLE_MAP.items()
        if expected_title in title_to_idx
    }
