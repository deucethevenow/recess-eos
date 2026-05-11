"""Leadership doc writer for /monday-kpi-update.

Per v3.8 Patch 3 (closes B6 leadership doc append):
  - Replaces the content between two sentinels:
      <<KPI_LEADERSHIP_START>>{content}<<KPI_LEADERSHIP_END>>
  - Fail loud if either sentinel is missing — never insertText append.
  - Default `max_sensitivity = "leadership"` (dept leads only).
  - Supports tabbed Google Docs: when sentinels live on a specific tab
    (e.g., "May 13th" tab in a recurring meeting agenda), the writer
    threads `tabId` through `deleteContentRange` and `insertText` so
    indexes resolve in the correct tab namespace.

Why this module diverges from `idempotency.build_replace_all_text_request`:

The helper in `idempotency` builds a single replaceAllText request whose
`containsText` is the empty sentinel pair (`<<START>><<END>>`). That works
for the first run (the doc literally contains the empty pair), but on
subsequent runs the doc contains `<<START>>{populated content}<<END>>` —
plain-text replaceAllText does NOT match this, so re-runs find 0
occurrences and silently no-op.

The structural approach used here:
  1. `documents.get(includeTabsContent=True)` to fetch the doc + every tab.
  2. Walk both legacy `body.content[]` and `tabs[].documentTab.body.content[]`
     (recursive over `childTabs[]`) to find the indexes of both sentinels.
  3. Build a `deleteContentRange` (clears between sentinels) +
     `insertText` (writes new content) request pair, threading `tabId`
     when the sentinels live on a non-default tab.

This works on every run regardless of the current section content. If the
sentinels are missing or out of order, we emit a failure alert and raise —
the doc owner must add the sentinel pair manually before re-running.

ASSUMPTIONS:
  - Each sentinel lives entirely within one textRun. Google Docs splits
    text into runs whenever styling changes (bold, italic, font, link,
    etc.). If a future operator copies the sentinels from a styled span
    and ends up with the start sentinel split across two runs (e.g.,
    "<<KPI_LEAD" in one run + "ERSHIP_START>>" in the next),
    `_find_sentinel_indexes` will not match and the writer will fail
    loud. Production sentinels are inserted as unstyled plain text —
    keep them that way.
  - Both sentinels live in the SAME tab. A start sentinel in tab A and
    end sentinel in tab B is a config error — indexes in different tabs
    are in different namespaces, so a single deleteContentRange cannot
    span them. The writer rejects that case and continues looking
    (potentially finding a properly-paired set later).
"""
from typing import Any, Dict, List, Optional, Tuple

from .failure_alert import emit_failure_alert
from .metric_payloads import MetricPayload, build_metric_payloads


def build_payloads_for_doc(
    meeting: dict,
    snapshot_row: dict,
    snapshot_timestamp: str,
) -> List[MetricPayload]:
    """Phase B+ surface adapter — Leadership-doc consumer's view of canonical payloads.

    Thin pass-through to the central producer. The existing sentinel-replacement
    rendering (deleteContentRange + insertText between <<KPI_LEADERSHIP_START>>
    and <<KPI_LEADERSHIP_END>>) is unchanged in Phase B+; this adapter exists so
    the cross-surface parity test can verify Leadership-doc consumes the same
    MetricPayload pipeline as Slack/Deck/Founders. DocRow text-cell synthesis
    lands in Phase C+E.
    """
    return build_metric_payloads(meeting, snapshot_row, snapshot_timestamp)

SENTINEL_START = "<<KPI_LEADERSHIP_START>>"
SENTINEL_END = "<<KPI_LEADERSHIP_END>>"


def _walk_text_runs(body: Dict[str, Any]):
    """Yield (startIndex, content) for every textRun in body.content order."""
    for elem in body.get("content", []) or []:
        para = elem.get("paragraph") or {}
        for pe in para.get("elements", []) or []:
            run = pe.get("textRun") or {}
            content = run.get("content")
            if content is None:
                continue
            yield pe.get("startIndex", 0), content


def _walk_tab_recursive(tab: Dict[str, Any]):
    """Yield (tab_id, run_start, content) for one tab + all its childTabs."""
    tab_id = (tab.get("tabProperties") or {}).get("tabId")
    doc_tab = tab.get("documentTab") or {}
    body = doc_tab.get("body") or {}
    for run_start, content in _walk_text_runs(body):
        yield tab_id, run_start, content
    for child in tab.get("childTabs", []) or []:
        yield from _walk_tab_recursive(child)


def _walk_doc_for_text_runs(doc: Dict[str, Any]):
    """Yield (tab_id, run_start, content) across the entire document.

    Handles both shapes:
      - Legacy single-body docs (or pre-tab API docs): `tab_id=None`,
        content from `doc.body.content[]`.
      - Tabbed docs (when fetched with `includeTabsContent=True`):
        `tab_id` from `tab.tabProperties.tabId`, content from
        `tab.documentTab.body.content[]` (recursive over `childTabs`).

    A doc may have BOTH the legacy `body` populated AND tabs (the legacy
    body is the first tab's content for backward compat). In that case
    we still yield both — the search loop in `_find_sentinel_indexes`
    handles the case where sentinels appear in the legacy view OR in a
    specific tab.
    """
    legacy_body = doc.get("body") or {}
    if legacy_body.get("content"):
        for run_start, content in _walk_text_runs(legacy_body):
            yield None, run_start, content
    for tab in doc.get("tabs", []) or []:
        yield from _walk_tab_recursive(tab)


def _find_sentinel_indexes(
    doc: Dict[str, Any],
    sentinel_start: str = SENTINEL_START,
    sentinel_end: str = SENTINEL_END,
) -> Optional[Tuple[int, int, Optional[str]]]:
    """Return (start_after_idx, end_before_idx, tab_id) or None if missing.

    `start_after_idx` is the doc position immediately AFTER the start sentinel.
    `end_before_idx` is the doc position immediately BEFORE the end sentinel.
    `tab_id` is the Google Docs tab ID where both sentinels were found, or
    `None` if found in the legacy single-body content (pre-tab docs OR the
    first tab's content as exposed via the legacy `body` field).

    Content to replace lives in [start_after_idx, end_before_idx) within
    the namespace of `tab_id`.

    If a start sentinel is found in tab A and the next end sentinel is in
    tab B, the start is treated as a false-positive (mismatched tab) and
    the search resets — both sentinels MUST share a tab for a clean
    delete-then-insert range. This protects against operator typos that
    place sentinels in different tabs.
    """
    pending_start: Optional[int] = None
    pending_tab_id: Optional[str] = None

    for tab_id, run_start, content in _walk_doc_for_text_runs(doc):
        if pending_start is None:
            pos = content.find(sentinel_start)
            if pos != -1:
                pending_start = run_start + pos + len(sentinel_start)
                pending_tab_id = tab_id
                # Look for end_sentinel in the SAME run after the start sentinel
                pos_end = content.find(sentinel_end, pos + len(sentinel_start))
                if pos_end != -1:
                    return (pending_start, run_start + pos_end, tab_id)
                continue
        else:
            # We have a pending start sentinel from an earlier run.
            if tab_id != pending_tab_id:
                # Sentinels in different tabs: indexes are in different
                # namespaces. Reset and keep looking for a proper pair.
                pending_start = None
                pending_tab_id = None
                # Fall through and treat THIS run as a fresh search.
                pos = content.find(sentinel_start)
                if pos != -1:
                    pending_start = run_start + pos + len(sentinel_start)
                    pending_tab_id = tab_id
                    pos_end = content.find(sentinel_end, pos + len(sentinel_start))
                    if pos_end != -1:
                        return (pending_start, run_start + pos_end, tab_id)
                continue
            pos_end = content.find(sentinel_end)
            if pos_end != -1:
                return (pending_start, run_start + pos_end, pending_tab_id)

    return None


def _build_section_text(
    rendered_per_dept: Dict[str, Dict[str, Any]],
    rocks_by_dept: Dict[str, Dict[str, list]],
    max_sensitivity: str,
) -> str:
    """Compose the leadership-doc section body from rendered rows + rocks.

    Local imports avoid pulling the dashboard repo at module-load.
    """
    from post_monday_pulse import (  # type: ignore
        _format_rock_line,
        _sensitivity_allowed,
    )

    lines: List[str] = []
    for dept_id, payload in rendered_per_dept.items():
        lines.append("")
        lines.append(f"{dept_id.replace('_', ' ').title()}")
        lines.append("-" * max(len(dept_id), 6))
        rows = [
            r
            for r in payload.get("scorecard_rows", [])
            if _sensitivity_allowed(r.sensitivity, max_sensitivity)
        ]
        for r in rows:
            lines.append(f"• {r.display_label}: {r.display}")
        rocks_section = rocks_by_dept.get(dept_id, {})
        rocks = rocks_section.get("rocks", [])
        projects = rocks_section.get("projects", [])
        if rocks:
            lines.append("Rocks:")
            lines.extend(_format_rock_line(r) for r in rocks)
        if projects:
            lines.append("Projects:")
            lines.extend(_format_rock_line(p) for p in projects)
    return "\n".join(lines)


def _range_for(start: int, end: int, tab_id: Optional[str]) -> Dict[str, Any]:
    r = {"startIndex": start, "endIndex": end}
    if tab_id:
        r["tabId"] = tab_id
    return r


def _location_for(idx: int, tab_id: Optional[str]) -> Dict[str, Any]:
    loc = {"index": idx}
    if tab_id:
        loc["tabId"] = tab_id
    return loc


def apply_to_leadership_doc(
    *,
    rendered_per_dept: Dict[str, Dict[str, Any]],
    rocks_by_dept: Dict[str, Dict[str, list]],
    doc_id: str,
    docs_service: Any,
    max_sensitivity: str = "leadership",
) -> int:
    """Replace the sentinel-delimited section with the rendered pulse.

    Returns the count of indexes replaced (always 1 on success — there's
    only one sentinel pair). Raises RuntimeError + emits failure alert if
    sentinels missing.

    Uses `includeTabsContent=True` so the writer finds sentinels regardless
    of whether they live in the legacy `body` or on a specific tab (e.g.,
    a recurring meeting agenda's "May 13" tab). When sentinels are on a
    tab, every batchUpdate request includes the tabId to keep indexes in
    the correct namespace.
    """
    doc = docs_service.documents().get(
        documentId=doc_id,
        includeTabsContent=True,
    ).execute()
    indexes = _find_sentinel_indexes(doc, SENTINEL_START, SENTINEL_END)
    if indexes is None:
        msg = (
            f"Sentinel pair {SENTINEL_START} / {SENTINEL_END} not found in "
            f"doc {doc_id}. Add the sentinel pair to the doc manually before "
            "re-running (and ensure both sentinels live on the SAME tab if "
            "the doc is tabbed). We will NOT fall back to insertText append "
            "— that would duplicate the section on every run (per Patch 3 "
            "contract)."
        )
        emit_failure_alert(surface="leadership_doc", detail=msg)
        raise RuntimeError(msg)

    start_after, end_before, tab_id = indexes
    body_text = "\n" + _build_section_text(
        rendered_per_dept, rocks_by_dept, max_sensitivity
    ) + "\n"

    requests: List[Dict[str, Any]] = []
    if end_before > start_after:
        requests.append(
            {"deleteContentRange": {"range": _range_for(start_after, end_before, tab_id)}}
        )
    requests.append(
        {
            "insertText": {
                "location": _location_for(start_after, tab_id),
                "text": body_text,
            }
        }
    )

    docs_service.documents().batchUpdate(
        documentId=doc_id, body={"requests": requests}
    ).execute()
    return 1


# =============================================================================
# Phase 2 — Table-aware leadership doc writer
# =============================================================================
#
# Operators set up tables in the doc with one row per metric. First column is
# the metric NAME (e.g., "Take Rate %"), used as the persistent row identifier.
# Other columns are field-typed by their header text (Target, Value, Status,
# Trend). On every run the writer:
#   1. Walks doc bodies (legacy + tabbed) to find table elements
#   2. Identifies each table's dept by scanning preceding heading text for a
#      known dept_id token. Falls back to `fallback_dept_id`.
#   3. Parses the header row → column_index → RenderedRow attribute name
#   4. For each data row, reads first cell → slugified metric name → finds the
#      matching RenderedRow in rendered_per_dept[dept]["scorecard_rows"]
#   5. Builds deleteContentRange + insertText requests for the Target/Value/
#      Status/Trend cells, processing in descending-index order so earlier
#      (lower-index) replacements don't invalidate later (higher-index) cell
#      indexes within the same batch.
#
# Placeholder convention (operator-facing):
#   {{kpi.<dept_id>.<metric_slug>.<field>}}  — first-run convenience only.
#   The writer doesn't read placeholders; it relies on the first column's
#   metric name + the column header field tag. After the first run, the
#   placeholders are gone (replaced with values); the writer keeps working
#   because the table structure is the persistent contract.


# Header-cell text (lowercased + stripped) → RenderedRow attribute name.
# None means "row identifier, never write here".
HEADER_TO_FIELD = {
    "metric": None,
    "metrics": None,
    "name": None,
    "value": "actual_display",
    "actual": "actual_display",
    "current": "actual_display",
    "target": "target_display",
    "goal": "target_display",
    "status": "status_icon",
    "trend": "trend_display",
}


# Operator-friendly metric names → canonical registry slugs.
# Operators picking labels that read best in meeting docs is a feature; the
# writer bridges to the registry-side canonical names here. Add an entry when
# you put a friendly label in a doc table that doesn't match the registry's
# canonical name.
SLUG_ALIASES: Dict[str, str] = {
    # Leadership pilot table aliases (2026-05-11)
    "nrr": "demand_nrr",
    "bookings_vs_goal": "bookings_goal_attainment",
    "net_revenue_vs_goal": "net_revenue_quota_attainment",
}


def _slugify_metric_name(name: str) -> str:
    """Convert a registry-style metric name to the placeholder/lookup slug.

    Mirrors the operator's manual placeholder construction:
      'Take Rate %'         -> 'take_rate'
      'NRR'                 -> 'nrr'
      'Pipeline Coverage'   -> 'pipeline_coverage'
      'Net Revenue vs Goal' -> 'net_revenue_vs_goal'
      'Weighted Pipeline $' -> 'weighted_pipeline'
    Drops everything that's not alphanumeric / whitespace / hyphen.
    """
    out = []
    for ch in name.lower():
        if ch.isalnum():
            out.append(ch)
        elif ch.isspace() or ch == "-":
            out.append("_")
    slug = "_".join(p for p in "".join(out).split("_") if p)
    return slug


def _table_cell_text(cell: Dict[str, Any]) -> str:
    """Concatenate all textRun content in a tableCell (plain text)."""
    parts: List[str] = []
    for elem in cell.get("content", []) or []:
        para = elem.get("paragraph") or {}
        for pe in para.get("elements", []) or []:
            run = pe.get("textRun") or {}
            content = run.get("content")
            if content:
                parts.append(content)
    return "".join(parts).strip()


def _walk_body_for_tables(body: Dict[str, Any], tab_id: Optional[str]):
    """Yield (tab_id, table_dict, preceding_paragraph_text) for each table.

    `preceding_paragraph_text` is the concatenated text of all paragraphs
    between this table and the previous table (or doc start). Used to
    detect which dept the table belongs to.
    """
    preceding_text = ""
    for elem in body.get("content", []) or []:
        if "table" in elem:
            yield (tab_id, elem["table"], preceding_text)
            preceding_text = ""
            continue
        para = elem.get("paragraph") or {}
        for pe in para.get("elements", []) or []:
            run = pe.get("textRun") or {}
            content = run.get("content") or ""
            preceding_text += content


def _walk_tab_for_tables(tab: Dict[str, Any]):
    tab_id = (tab.get("tabProperties") or {}).get("tabId")
    doc_tab = tab.get("documentTab") or {}
    body = doc_tab.get("body") or {}
    yield from _walk_body_for_tables(body, tab_id)
    for child in tab.get("childTabs", []) or []:
        yield from _walk_tab_for_tables(child)


def _walk_doc_for_tables(doc: Dict[str, Any]):
    """Yield (tab_id, table, preceding_text) for every table in the doc."""
    legacy_body = doc.get("body") or {}
    if legacy_body.get("content"):
        yield from _walk_body_for_tables(legacy_body, tab_id=None)
    for tab in doc.get("tabs", []) or []:
        yield from _walk_tab_for_tables(tab)


def _detect_dept_id_from_text(
    preceding_text: str,
    known_dept_ids: List[str],
    fallback: str,
) -> str:
    """Find which known dept_id appears in the text immediately before a table.

    Matches case-insensitively. Tries the dept_id verbatim AND with underscores
    replaced by spaces (so "demand_am" matches "Demand AM" or "demand am").
    Returns the first matched dept_id, or `fallback` if none match.
    """
    text_lower = preceding_text.lower()
    for dept_id in known_dept_ids:
        if dept_id.lower() in text_lower:
            return dept_id
        spaced = dept_id.replace("_", " ").lower()
        if spaced and spaced in text_lower:
            return dept_id
    return fallback


def apply_to_leadership_doc_tables(
    *,
    rendered_per_dept: Dict[str, Dict[str, Any]],
    doc_id: str,
    docs_service: Any,
    fallback_dept_id: str = "leadership",
) -> Dict[str, Any]:
    """Populate KPI tables in the leadership Google Doc.

    For each `table` element in the doc:
      - Detect dept (from preceding heading text, fallback otherwise)
      - Build column-index → field map from header row
      - For each data row, slug-match the first cell against rendered_per_dept's
        scorecard_rows, then write Target / Value / Status / Trend cells

    Index-shift safety: cell updates are collected with their original indexes,
    then submitted in descending-index order so each delete+insert pair operates
    on a position that hasn't been disturbed by earlier (higher-index) requests.

    Returns: dict with `tables_found`, `cells_updated`, `rows_matched`,
    `rows_unmatched`, and `by_dept` (per-dept update counts).
    """
    doc = docs_service.documents().get(
        documentId=doc_id,
        includeTabsContent=True,
    ).execute()

    known_dept_ids = list(rendered_per_dept.keys())

    # Each entry: (original_start_index, request_dict). Sort descending later
    # so the API processes the highest indexes first and doesn't shift the
    # positions of the lower-index cells we still need to touch.
    pending: List[Tuple[int, Dict[str, Any]]] = []

    tables_found = 0
    cells_updated = 0
    rows_matched = 0
    rows_unmatched = 0
    by_dept: Dict[str, int] = {}

    for tab_id, table, preceding_text in _walk_doc_for_tables(doc):
        rows = table.get("tableRows", []) or []
        if len(rows) < 2:
            continue  # Need at least header + 1 data row

        # Parse header row first — and ONLY treat this as a KPI table if the
        # first column header is in our known label set ("Metric" / "Metrics" /
        # "Name"). Without this gate, the writer would walk every table in
        # the doc (meeting notes, action items, etc.) and write metric data
        # into any cell whose column header matched a field name.
        header_cells = rows[0].get("tableCells", []) or []
        if not header_cells:
            continue
        first_header = _table_cell_text(header_cells[0]).lower()
        if HEADER_TO_FIELD.get(first_header, "MISSING") is not None:
            # First-column header is NOT a row-identifier label (None mapping).
            # Either it's an unknown header (not "Metric"/"Metrics"/"Name") or
            # it's a field header in the wrong column — skip the table.
            continue

        dept_id = _detect_dept_id_from_text(
            preceding_text, known_dept_ids, fallback_dept_id
        )
        if dept_id not in rendered_per_dept:
            continue
        tables_found += 1

        # Build column-index → field map (skip column 0 — it's the metric label)
        col_to_field: Dict[int, Optional[str]] = {}
        for col_idx, cell in enumerate(header_cells):
            header_text = _table_cell_text(cell).lower()
            col_to_field[col_idx] = HEADER_TO_FIELD.get(header_text)

        # Build metric lookup
        scorecard_rows = rendered_per_dept[dept_id].get("scorecard_rows", []) or []
        rows_by_slug = {
            _slugify_metric_name(r.metric_name): r for r in scorecard_rows
        }

        # Process each data row
        for data_row in rows[1:]:
            cells = data_row.get("tableCells", []) or []
            if not cells:
                continue

            metric_text = _table_cell_text(cells[0])
            slug = _slugify_metric_name(metric_text)
            if not slug:
                continue
            # Try direct slug match first; fall back to operator-alias map.
            row_obj = rows_by_slug.get(slug)
            if row_obj is None:
                aliased = SLUG_ALIASES.get(slug)
                if aliased:
                    row_obj = rows_by_slug.get(aliased)
            if row_obj is None:
                rows_unmatched += 1
                continue
            rows_matched += 1

            for col_idx, cell in enumerate(cells):
                if col_idx == 0:
                    continue  # Never touch the metric-name column
                field = col_to_field.get(col_idx)
                if not field:
                    continue
                value = getattr(row_obj, field, None)
                value_str = str(value) if value is not None else "—"

                cell_start = cell.get("startIndex")
                cell_end = cell.get("endIndex")
                if cell_start is None or cell_end is None:
                    continue

                content_start = cell_start + 1
                content_end = cell_end - 1

                if content_end > content_start:
                    pending.append((content_start, {
                        "deleteContentRange": {
                            "range": _range_for(content_start, content_end, tab_id),
                        }
                    }))
                pending.append((content_start, {
                    "insertText": {
                        "location": _location_for(content_start, tab_id),
                        "text": value_str,
                    }
                }))
                cells_updated += 1
                by_dept[dept_id] = by_dept.get(dept_id, 0) + 1

    summary = {
        "tables_found": tables_found,
        "cells_updated": cells_updated,
        "rows_matched": rows_matched,
        "rows_unmatched": rows_unmatched,
        "by_dept": by_dept,
    }

    if not pending:
        if tables_found == 0:
            emit_failure_alert(
                surface="leadership_doc_tables",
                detail=(
                    f"No KPI tables found in doc {doc_id}. Operator must add at "
                    "least one table with header row [Metric, Target, Value, "
                    "Status, Trend] and a metric name in the first cell of each "
                    "data row. Falling back to no-op."
                ),
            )
        return summary

    # Descending-index sort: highest indexes processed first. Python's stable
    # sort preserves the delete-then-insert pairing within each cell (delete
    # was appended first → comes first in the sorted output when indexes tie).
    pending.sort(key=lambda x: x[0], reverse=True)
    requests = [r for _, r in pending]

    docs_service.documents().batchUpdate(
        documentId=doc_id, body={"requests": requests}
    ).execute()
    return summary
