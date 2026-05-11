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
