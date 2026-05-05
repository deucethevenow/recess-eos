"""Slides API deck writer for /monday-kpi-update.

Per v3.8 Patch 1 + Patch 3 + Patch 4 (Session 3 wiring):
  - Reads RenderedRow.display_label + RenderedRow.display ONLY. The writer
    never re-formats values, never recomputes targets, never resolves its
    own per-dept label. Cross-output parity is enforced by the contract.
  - Every cell write goes through `idempotency.write_cell` which pairs
    deleteText (full range) + insertText (insertionIndex=0). Without this
    pairing, repeat runs accumulate trailing newlines per Slides API
    semantics.
  - Per-slide try/except: if any one dept's write fails, the others continue.
    `failure_alert.emit_failure_alert` posts a structured signal to
    `#kpi-dashboard-notifications` so on-call sees which dept and which slide.
  - `build_table_row_count_fetcher` returns a closure suitable for injecting
    into `preflight.run_preflight` — it caches the presentation fetch per
    deck_id so a 7-dept run hits the Slides API exactly once for row counts.

Cell layout per dept slide:
  Row 0 = header (untouched by writer; shaped during manual prep).
  Row 1..N = one row per RenderedRow:
    Col 0 = display_label
    Col 1 = display
"""
from typing import Any, Callable, Dict, Iterable, List, Optional

from .failure_alert import emit_failure_alert
from .idempotency import write_cell


def _filter_visible_rows(rows: Iterable, max_sensitivity: str) -> List:
    """Drop rows whose sensitivity exceeds `max_sensitivity`.

    Imported lazily so this module doesn't pull in the dashboard repo at
    module-load — keeps the deck writer importable in environments that
    only need build_table_row_count_fetcher.
    """
    from post_monday_pulse import _sensitivity_allowed  # type: ignore

    return [r for r in rows if _sensitivity_allowed(r.sensitivity, max_sensitivity)]


def _resolve_table_object_id(
    slide: Dict[str, Any],
) -> Optional[str]:
    """Find the first table on the slide and return its object_id.

    Pre-flight Patch 5 already guarantees there's a table on every dept
    slide before we get here — but we still return None defensively so
    the per-slide try/except can emit a clean failure alert.
    """
    for el in slide.get("pageElements", []) or []:
        if "table" in el:
            return el.get("objectId")
    return None


def apply_via_slides_api(
    *,
    rendered_per_dept: Dict[str, Dict[str, Any]],
    max_sensitivity: str,
    slides_service: Any,
    presentation_id: str,
    presentation: Optional[Dict[str, Any]] = None,
) -> None:
    """Write each dept's RenderedRow.display values into its scorecard slide table.

    `presentation` may be passed pre-fetched (e.g., from preflight's row-count
    fetcher) to avoid re-fetching. Otherwise the function fetches it once
    upfront — a 7-dept run still hits Slides API only once.
    """
    if presentation is None:
        presentation = (
            slides_service.presentations().get(presentationId=presentation_id).execute()
        )

    slides = presentation.get("slides", []) or []

    for dept_id, payload in rendered_per_dept.items():
        slide_idx = payload.get("slide_idx")
        if slide_idx is None:
            continue  # preflight already surfaced this when skip_deck=False
        if slide_idx >= len(slides):
            emit_failure_alert(
                surface="deck",
                detail=f"slide_idx {slide_idx} out of range (deck has {len(slides)} slides).",
                dept=dept_id,
                slide_idx=slide_idx,
            )
            continue

        rows = _filter_visible_rows(payload.get("scorecard_rows", []), max_sensitivity)

        try:
            slide = slides[slide_idx]
            table_id = _resolve_table_object_id(slide)
            if table_id is None:
                emit_failure_alert(
                    surface="deck",
                    detail="No table object found on slide.",
                    dept=dept_id,
                    slide_idx=slide_idx,
                )
                continue
            for offset, row in enumerate(rows):
                table_row = 1 + offset  # row 0 reserved for header
                write_cell(
                    slides_service,
                    presentation_id,
                    table_id,
                    table_row,
                    0,
                    row.display_label,
                )
                write_cell(
                    slides_service,
                    presentation_id,
                    table_id,
                    table_row,
                    1,
                    row.display,
                )
        except Exception as e:  # noqa: BLE001 — per-slide isolation per Patch 4d
            emit_failure_alert(
                surface="deck",
                detail=f"per-slide write failed for {dept_id}",
                exc=e,
                dept=dept_id,
                slide_idx=slide_idx,
            )


def build_table_row_count_fetcher(
    slides_service: Any,
) -> Callable[[str, int], Optional[int]]:
    """Returns `fetch_table_row_count(deck_id, slide_idx) -> Optional[int]`
    suitable for `preflight.run_preflight` injection.

    Caches the presentation fetch per deck_id so a 7-dept preflight run hits
    Slides API exactly once. Re-fetches across `deck_id` boundaries so a
    test/prod swap doesn't return stale rows.
    """
    pres_cache: Dict[str, Dict[str, Any]] = {}

    def fetcher(deck_id: str, slide_index: int) -> Optional[int]:
        pres = pres_cache.get(deck_id)
        if pres is None:
            pres = (
                slides_service.presentations().get(presentationId=deck_id).execute()
            )
            pres_cache[deck_id] = pres
        slides = pres.get("slides", []) or []
        if slide_index >= len(slides):
            return None
        slide = slides[slide_index]
        for el in slide.get("pageElements", []) or []:
            if "table" in el:
                rows = el["table"].get("tableRows", []) or []
                return len(rows)
        return None

    return fetcher
