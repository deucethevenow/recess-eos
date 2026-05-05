"""Leadership doc writer for /monday-kpi-update.

Per v3.8 Patch 3 (closes B6 leadership doc append):
  - Replaces the content between two sentinels:
      <<KPI_LEADERSHIP_START>>{content}<<KPI_LEADERSHIP_END>>
  - Fail loud if either sentinel is missing — never insertText append.
  - Default `max_sensitivity = "leadership"` (dept leads only).

Why this module diverges from `idempotency.build_replace_all_text_request`:

The helper in `idempotency` builds a single replaceAllText request whose
`containsText` is the empty sentinel pair (`<<START>><<END>>`). That works
for the first run (the doc literally contains the empty pair), but on
subsequent runs the doc contains `<<START>>{populated content}<<END>>` —
plain-text replaceAllText does NOT match this, so re-runs find 0
occurrences and silently no-op.

The structural approach used here:
  1. `documents.get()` to fetch the doc body.
  2. Walk paragraph elements to find the indexes of both sentinels.
  3. Build a `deleteContentRange` (clears between sentinels) +
     `insertText` (writes new content) request pair.

This works on every run regardless of the current section content. If the
sentinels are missing or out of order, we emit a failure alert and raise —
the doc owner must add the sentinel pair manually before re-running.

ASSUMPTION: each sentinel lives entirely within one textRun. Google Docs
splits text into runs whenever styling changes (bold, italic, font, link,
etc.). If a future operator copies the sentinels from a styled span and
ends up with the start sentinel split across two runs (e.g., "<<KPI_LEAD"
in one run + "ERSHIP_START>>" in the next), `_find_sentinel_indexes` will
not match and the writer will fail loud at the "sentinel pair not found"
check. Production sentinels are inserted as unstyled plain text — keep
them that way. If multi-run support becomes a real need, switch to
concatenating the body's plain text and tracking run-offsets.
"""
from typing import Any, Dict, List, Optional, Tuple

from .failure_alert import emit_failure_alert

SENTINEL_START = "<<KPI_LEADERSHIP_START>>"
SENTINEL_END = "<<KPI_LEADERSHIP_END>>"


def _walk_text_runs(body: Dict[str, Any]):
    """Yield (startIndex, content) for every textRun in document order."""
    for elem in body.get("content", []) or []:
        para = elem.get("paragraph") or {}
        for pe in para.get("elements", []) or []:
            run = pe.get("textRun") or {}
            content = run.get("content")
            if content is None:
                continue
            yield pe.get("startIndex", 0), content


def _find_sentinel_indexes(
    doc: Dict[str, Any],
    sentinel_start: str = SENTINEL_START,
    sentinel_end: str = SENTINEL_END,
) -> Optional[Tuple[int, int]]:
    """Return (start_after_idx, end_before_idx) or None if either sentinel missing.

    `start_after_idx` is the doc position immediately AFTER the start sentinel.
    `end_before_idx` is the doc position immediately BEFORE the end sentinel.
    Content to replace lives in [start_after_idx, end_before_idx).
    """
    body = doc.get("body") or {}
    start_after: Optional[int] = None
    end_before: Optional[int] = None
    for run_start, content in _walk_text_runs(body):
        if start_after is None:
            pos = content.find(sentinel_start)
            if pos != -1:
                start_after = run_start + pos + len(sentinel_start)
                # Look for end_sentinel in the SAME run after the start sentinel
                pos_end = content.find(sentinel_end, pos + len(sentinel_start))
                if pos_end != -1:
                    end_before = run_start + pos_end
                    return (start_after, end_before)
                continue
        # start_after already known; search remaining runs for end sentinel
        pos_end = content.find(sentinel_end)
        if pos_end != -1:
            end_before = run_start + pos_end
            return (start_after, end_before)

    if start_after is None or end_before is None:
        return None
    return (start_after, end_before)


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
    """
    doc = docs_service.documents().get(documentId=doc_id).execute()
    indexes = _find_sentinel_indexes(doc, SENTINEL_START, SENTINEL_END)
    if indexes is None:
        msg = (
            f"Sentinel pair {SENTINEL_START} / {SENTINEL_END} not found in "
            f"doc {doc_id}. Add the sentinel pair to the doc manually before "
            "re-running. We will NOT fall back to insertText append — that "
            "would duplicate the section on every run (per Patch 3 contract)."
        )
        emit_failure_alert(surface="leadership_doc", detail=msg)
        raise RuntimeError(msg)

    start_after, end_before = indexes
    body_text = "\n" + _build_section_text(
        rendered_per_dept, rocks_by_dept, max_sensitivity
    ) + "\n"

    requests: List[Dict[str, Any]] = []
    if end_before > start_after:
        requests.append(
            {
                "deleteContentRange": {
                    "range": {
                        "startIndex": start_after,
                        "endIndex": end_before,
                    }
                }
            }
        )
    requests.append(
        {
            "insertText": {
                "location": {"index": start_after},
                "text": body_text,
            }
        }
    )

    docs_service.documents().batchUpdate(
        documentId=doc_id, body={"requests": requests}
    ).execute()
    return 1
