"""Patch 3 contract tests — idempotency per surface.

  - Slack: once-per-day Firestore marker.
  - Deck: every cell write is a paired deleteText + insertText.
  - Leadership doc: replaceAllText with sentinel pair, never insertText append.
"""
from datetime import date
from unittest.mock import MagicMock

from lib.idempotency import (
    build_cell_write_requests,
    build_replace_all_text_request,
    mark_slack_posted,
    slack_already_posted_today,
)


# ----- Deck: deleteText must precede insertText for every cell write -------- #


def test_cell_write_emits_deletetext_before_inserttext():
    requests = build_cell_write_requests("table_obj_1", row=2, col=1, text="hello")
    assert len(requests) == 2
    assert "deleteText" in requests[0]
    assert "insertText" in requests[1]


def test_cell_write_deletetext_targets_cell_with_all_range():
    requests = build_cell_write_requests("table_obj_1", row=3, col=2, text="x")
    delete_req = requests[0]["deleteText"]
    assert delete_req["objectId"] == "table_obj_1"
    assert delete_req["cellLocation"] == {"rowIndex": 3, "columnIndex": 2}
    assert delete_req["textRange"] == {"type": "ALL"}


def test_cell_write_inserttext_uses_insertion_index_zero():
    """If insertionIndex is non-zero, the text accumulates after pre-existing
    content. Index 0 plus the preceding deleteText guarantees idempotency."""
    requests = build_cell_write_requests("t", row=0, col=0, text="$1.04M")
    insert_req = requests[1]["insertText"]
    assert insert_req["insertionIndex"] == 0
    assert insert_req["text"] == "$1.04M"


def test_repeat_cell_write_yields_identical_request_payload():
    """Run the helper twice — payload bytes are equal. (The Slides API request
    is itself idempotent given the deleteText prefix; this asserts the
    helper does not introduce any per-call drift.)"""
    a = build_cell_write_requests("t", 0, 0, "x")
    b = build_cell_write_requests("t", 0, 0, "x")
    assert a == b


# ----- Leadership doc: replaceAllText with sentinels ----------------------- #


def test_replace_all_text_request_uses_sentinel_pair_not_append():
    req = build_replace_all_text_request(
        sentinel_start="<<KPI_LEADERSHIP_START>>",
        sentinel_end="<<KPI_LEADERSHIP_END>>",
        replacement="rendered block",
    )
    assert "replaceAllText" in req
    inner = req["replaceAllText"]
    assert "containsText" in inner
    # The replacement preserves the sentinel pair so future runs find it again.
    assert "<<KPI_LEADERSHIP_START>>" in inner["replaceText"]
    assert "<<KPI_LEADERSHIP_END>>" in inner["replaceText"]
    assert "rendered block" in inner["replaceText"]


def test_replace_all_text_match_case_is_true():
    req = build_replace_all_text_request("<<A>>", "<<B>>", "x")
    assert req["replaceAllText"]["containsText"]["matchCase"] is True


# ----- Slack: Firestore once-per-day marker -------------------------------- #


def _make_doc(exists, data=None):
    doc = MagicMock()
    doc.exists = exists
    doc.to_dict.return_value = data or {}
    return doc


def test_slack_already_posted_returns_true_when_marker_present():
    fake_db = MagicMock()
    fake_db.collection.return_value.document.return_value.get.return_value = _make_doc(
        exists=True, data={"slack_posted": True}
    )
    assert slack_already_posted_today(date(2026, 5, 5), client=fake_db) is True


def test_slack_already_posted_returns_false_when_doc_missing():
    fake_db = MagicMock()
    fake_db.collection.return_value.document.return_value.get.return_value = _make_doc(
        exists=False
    )
    assert slack_already_posted_today(date(2026, 5, 5), client=fake_db) is False


def test_slack_already_posted_returns_false_when_marker_field_missing():
    fake_db = MagicMock()
    fake_db.collection.return_value.document.return_value.get.return_value = _make_doc(
        exists=True, data={"some_other_field": "x"}
    )
    assert slack_already_posted_today(date(2026, 5, 5), client=fake_db) is False


def test_mark_slack_posted_writes_with_merge_true(monkeypatch):
    """Merge true is required so a separate marker (e.g., deck_posted) on the
    same doc isn't clobbered."""
    fake_db = MagicMock()
    fake_doc = MagicMock()
    fake_db.collection.return_value.document.return_value = fake_doc

    # google.cloud.firestore is referenced inside mark_slack_posted for SERVER_TIMESTAMP;
    # patch the module so the import succeeds without google-cloud-firestore installed.
    fake_firestore = MagicMock()
    fake_firestore.SERVER_TIMESTAMP = "SENTINEL"
    monkeypatch.setitem(__import__("sys").modules, "google.cloud", MagicMock(firestore=fake_firestore))
    monkeypatch.setitem(__import__("sys").modules, "google.cloud.firestore", fake_firestore)

    mark_slack_posted(date(2026, 5, 5), ts="1234567.890", channel="C0AQP3WH7AB", client=fake_db)
    args, kwargs = fake_doc.set.call_args
    assert kwargs == {"merge": True}
    payload = args[0]
    assert payload["slack_posted"] is True
    assert payload["ts"] == "1234567.890"
    assert payload["channel"] == "C0AQP3WH7AB"
