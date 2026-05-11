"""Per-surface idempotency contracts for /monday-kpi-update.

Per v3.8 Patch 3 (closes B4 Slack repost, B5 deck newline accumulation, B6 leadership
doc append):
  - Slack: once-per-day Firestore marker at monday_kpi_update_runs/{date}.
  - Deck: every cell write is a paired deleteText (full range) + insertText.
          Without this, run 2 yields "text\n", run 3 yields "text\ntext\n".
  - Leadership doc: replaceAllText with sentinel pair, never insertText append.

The Firestore client is constructed against database="kpi-dashboard" (the named
database used by the dashboard, NOT the (default) Datastore-mode database — see
CLAUDE.md auto-memory entry "Firestore on stitchdata-384118").
"""
from datetime import date as _date
from typing import Any, Dict, List, Optional

PROJECT_ID = "stitchdata-384118"
FIRESTORE_DB = "kpi-dashboard"
COLLECTION = "monday_kpi_update_runs"


def _firestore_client():
    from google.cloud import firestore  # imported lazily so unit tests can mock it

    return firestore.Client(project=PROJECT_ID, database=FIRESTORE_DB)


def slack_already_posted_today(run_date: _date, client=None) -> bool:
    db = client or _firestore_client()
    doc = db.collection(COLLECTION).document(run_date.isoformat()).get()
    if not doc.exists:
        return False
    return bool(doc.to_dict().get("slack_posted") is True)


def mark_slack_posted(
    run_date: _date,
    ts: str,
    channel: str,
    client=None,
) -> None:
    from google.cloud import firestore

    db = client or _firestore_client()
    db.collection(COLLECTION).document(run_date.isoformat()).set(
        {
            "slack_posted": True,
            "ts": ts,
            "channel": channel,
            "posted_at": firestore.SERVER_TIMESTAMP,
        },
        merge=True,
    )


def build_cell_write_requests(
    table_object_id: str,
    row: int,
    col: int,
    text: str,
    cell_is_empty: bool = False,
) -> List[Dict[str, Any]]:
    """Build requests to write `text` into one table cell, idempotent on re-run.

    Slides API insertText accumulates a trailing newline per call, so we MUST
    deleteText before inserting whenever the cell already has content. But the
    Slides API REJECTS deleteText on an empty cell: `textRange: ALL` resolves
    to a zero-length range, and the API enforces startIndex < endIndex.

    Caller must inspect the cell first and pass `cell_is_empty=True` for cells
    with no text. First-run writes against pre-padded scorecard slides hit
    this case for every metric row. Re-runs hit `cell_is_empty=False` and need
    the deleteText pair.
    """
    insert_request = {
        "insertText": {
            "objectId": table_object_id,
            "cellLocation": {"rowIndex": row, "columnIndex": col},
            "text": text,
            "insertionIndex": 0,
        }
    }
    if cell_is_empty:
        return [insert_request]
    return [
        {
            "deleteText": {
                "objectId": table_object_id,
                "cellLocation": {"rowIndex": row, "columnIndex": col},
                "textRange": {"type": "ALL"},
            }
        },
        insert_request,
    ]


def write_cell(
    slides_service,
    presentation_id: str,
    table_object_id: str,
    row: int,
    col: int,
    text: str,
    cell_is_empty: bool = False,
) -> None:
    requests = build_cell_write_requests(
        table_object_id, row, col, text, cell_is_empty=cell_is_empty
    )
    slides_service.presentations().batchUpdate(
        presentationId=presentation_id, body={"requests": requests}
    ).execute()


def build_replace_all_text_request(
    sentinel_start: str,
    sentinel_end: str,
    replacement: str,
) -> Dict[str, Any]:
    """Single replaceAllText for a leadership-doc managed section.

    The sentinels delimit one named section. Re-runs replace the same span,
    so the doc length is stable. If the sentinels are missing the writer
    must FAIL LOUD — never fall back to insertText append (which would
    duplicate the section on every run).
    """
    return {
        "replaceAllText": {
            "containsText": {"text": f"{sentinel_start}{sentinel_end}", "matchCase": True},
            "replaceText": f"{sentinel_start}{replacement}{sentinel_end}",
        }
    }
