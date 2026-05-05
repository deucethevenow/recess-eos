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

Cell layout per dept slide (5-column scorecard):
  Row 0 = header (untouched by writer; shaped during manual prep).
  Row 1..N = one row per RenderedRow:
    Col 0 = Metric → display_label
    Col 1 = Target → target_display (Session 3.7: now populated)
    Col 2 = Actual → actual_display (the value WITHOUT trailing target suffix)
    Col 3 = Status → status_icon (⚪ in Phase 1; on/off-track in Phase 2)
    Col 4 = Trend  → blank (Phase 2 will populate from a trend computation)

The Trend column stays blank in Phase 1 — computing pace/gap requires
quarter-progress math against target_raw + actual_raw which the cron's
render path doesn't expose today. Status stays neutral (⚪) until the
target/actual numeric comparison is wired.
"""
from typing import Any, Callable, Dict, Iterable, List, Optional

from .failure_alert import emit_failure_alert
from .idempotency import build_cell_write_requests


def _filter_visible_rows(rows: Iterable, max_sensitivity: str) -> List:
    """Drop rows whose sensitivity exceeds `max_sensitivity`.

    Imported lazily so this module doesn't pull in the dashboard repo at
    module-load — keeps the deck writer importable in environments that
    only need build_table_row_count_fetcher.
    """
    from post_monday_pulse import _sensitivity_allowed  # type: ignore

    return [r for r in rows if _sensitivity_allowed(r.sensitivity, max_sensitivity)]


def _resolve_table_object(
    slide: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    """Find the first table element on the slide and return the full element.

    Returns the pageElement dict containing both `objectId` and `table.tableRows[]`,
    or None if no table is on the slide. The full element is needed so the
    writer can inspect existing cell text to decide whether to include a
    `deleteText` request (which fails on empty cells with a Slides API
    `startIndex < endIndex` error).
    """
    for el in slide.get("pageElements", []) or []:
        if "table" in el:
            return el
    return None


def _resolve_table_object_id(
    slide: Dict[str, Any],
) -> Optional[str]:
    """Backward-compat shim — returns just the objectId of the first table."""
    el = _resolve_table_object(slide)
    return el.get("objectId") if el else None


def _cell_is_empty(table: Dict[str, Any], row_idx: int, col_idx: int) -> bool:
    """Return True if the cell at [row_idx, col_idx] has no text content.

    Slides API quirk: `deleteText` with `textRange.type=ALL` rejects empty
    cells (zero-length range). Pre-padded scorecard slides have empty cells
    on first run, so the writer must skip `deleteText` for those.
    """
    try:
        cell = table["tableRows"][row_idx]["tableCells"][col_idx]
    except (KeyError, IndexError, TypeError):
        return True  # missing cell ⇒ behave as empty (skip deleteText)
    text_obj = cell.get("text") or {}
    for te in text_obj.get("textElements", []) or []:
        tr = te.get("textRun") or {}
        if tr.get("content"):
            return False
    return True


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
            table_elem = _resolve_table_object(slide)
            if table_elem is None:
                emit_failure_alert(
                    surface="deck",
                    detail="No table object found on slide.",
                    dept=dept_id,
                    slide_idx=slide_idx,
                )
                continue
            table_id = table_elem.get("objectId")
            table = table_elem.get("table") or {}

            # Collect ALL requests for this dept's slide in one batch — sends
            # a single batchUpdate per dept instead of one per cell. Reduces
            # API call count from ~4*N to 1 per dept.
            requests: List[Dict[str, Any]] = []
            for offset, row in enumerate(rows):
                table_row = 1 + offset  # row 0 reserved for header
                # Phase 1 writes 4 of the deck's 5 columns:
                #   col 0 = Metric  → display_label
                #   col 1 = Target  → target_display (None → empty string)
                #   col 2 = Actual  → actual_display (value WITHOUT target suffix)
                #   col 3 = Status  → status_icon
                # Col 4 (Trend) is Phase 2.
                cell_writes = [
                    (0, row.display_label),
                    (1, row.target_display or ""),
                    (2, row.actual_display),
                    (3, row.status_icon),
                ]
                for col, text in cell_writes:
                    if not text and _cell_is_empty(table, table_row, col):
                        # Skip cells that are already empty AND we have nothing
                        # to write. Writing empty insertText is a no-op and
                        # wastes an API request slot.
                        continue
                    is_empty = _cell_is_empty(table, table_row, col)
                    requests.extend(
                        build_cell_write_requests(
                            table_id, table_row, col, text, cell_is_empty=is_empty
                        )
                    )

            if requests:
                slides_service.presentations().batchUpdate(
                    presentationId=presentation_id, body={"requests": requests}
                ).execute()
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
