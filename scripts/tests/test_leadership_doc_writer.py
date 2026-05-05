"""Session 3 contract tests — leadership_doc_writer.

Asserts the four invariants of apply_to_leadership_doc:
  1. Reads doc, finds sentinel pair indexes, builds deleteContentRange + insertText.
  2. Fail loud (RuntimeError + failure alert) when sentinels missing —
     NEVER falls back to insertText append.
  3. Empty span (sentinels juxtaposed) → just insertText, no deleteContentRange.
  4. Sensitivity filter applied before composing section text.
"""
from unittest.mock import MagicMock

import pytest

from lib import leadership_doc_writer
from lib.leadership_doc_writer import (
    SENTINEL_END,
    SENTINEL_START,
    _find_sentinel_indexes,
    apply_to_leadership_doc,
)
from lib.rendered_row import RenderedRow


def _row(name, sensitivity="public", display="$1"):
    return RenderedRow(
        metric_name=name,
        display_label=name,
        dept_id="leadership",
        sensitivity=sensitivity,
        actual_raw=None,
        target_raw=None,
        status_icon="⚪",
        display=display,
        actual_display=display,
        target_display=None,
        is_phase2_placeholder=False,
        is_special_override=False,
    )


def _doc_with_sentinels(content_between=""):
    """Build a fake Google Docs response with the sentinel pair at known indexes.

    The doc body has a single paragraph whose text is:
        Header text\n<<KPI_LEADERSHIP_START>>{content_between}<<KPI_LEADERSHIP_END>>\nFooter
    """
    full_text = (
        f"Header text\n"
        f"{SENTINEL_START}{content_between}{SENTINEL_END}\n"
        f"Footer"
    )
    return {
        "body": {
            "content": [
                {
                    "paragraph": {
                        "elements": [
                            {
                                "startIndex": 1,
                                "endIndex": 1 + len(full_text),
                                "textRun": {"content": full_text},
                            }
                        ]
                    }
                }
            ]
        }
    }


def _doc_without_sentinels():
    return {
        "body": {
            "content": [
                {
                    "paragraph": {
                        "elements": [
                            {
                                "startIndex": 1,
                                "endIndex": 12,
                                "textRun": {"content": "No sentinels"},
                            }
                        ]
                    }
                }
            ]
        }
    }


def _make_docs_service(doc_response):
    service = MagicMock()
    service.documents.return_value.get.return_value.execute.return_value = (
        doc_response
    )
    service.documents.return_value.batchUpdate.return_value.execute.return_value = {}
    return service


# ----- _find_sentinel_indexes --------------------------------------------- #


def test_find_sentinel_indexes_locates_both_with_content_between():
    doc = _doc_with_sentinels(content_between="some content")
    indexes = _find_sentinel_indexes(doc)
    assert indexes is not None
    start_after, end_before, tab_id = indexes
    # start_after must be GREATER than end_before? No — start_after should be
    # the position just after START sentinel, end_before is just before END.
    assert end_before > start_after
    # The span between them should be the length of "some content".
    assert end_before - start_after == len("some content")
    # Legacy body fixture has no tabs → tab_id is None
    assert tab_id is None


def test_find_sentinel_indexes_returns_none_when_missing():
    doc = _doc_without_sentinels()
    assert _find_sentinel_indexes(doc) is None


def test_find_sentinel_indexes_handles_empty_span():
    """Empty span = sentinels juxtaposed = first-run state."""
    doc = _doc_with_sentinels(content_between="")
    indexes = _find_sentinel_indexes(doc)
    assert indexes is not None
    start_after, end_before, tab_id = indexes
    assert end_before == start_after  # zero-length span
    assert tab_id is None


# ----- apply_to_leadership_doc -------------------------------------------- #


def test_apply_replaces_span_with_delete_then_insert():
    rendered = {"leadership": {"scorecard_rows": [_row("X", display="$100")]}}
    rocks = {"leadership": {"rocks": [], "projects": []}}
    doc = _doc_with_sentinels(content_between="OLD CONTENT")
    service = _make_docs_service(doc)

    occurrences = apply_to_leadership_doc(
        rendered_per_dept=rendered,
        rocks_by_dept=rocks,
        doc_id="DOC_X",
        docs_service=service,
        max_sensitivity="leadership",
    )

    assert occurrences == 1
    # Inspect the batchUpdate request payload.
    call = service.documents.return_value.batchUpdate.call_args
    body = call.kwargs.get("body") or call.args[1]
    requests = body["requests"]
    # Must have BOTH deleteContentRange and insertText (in that order).
    assert "deleteContentRange" in requests[0]
    assert "insertText" in requests[1]
    # insertText payload must contain the rendered display value.
    assert "$100" in requests[1]["insertText"]["text"]


def test_apply_skips_delete_for_empty_span():
    """First-run case: no content between sentinels → no deleteContentRange."""
    rendered = {"leadership": {"scorecard_rows": [_row("X", display="$1")]}}
    rocks = {"leadership": {"rocks": [], "projects": []}}
    doc = _doc_with_sentinels(content_between="")
    service = _make_docs_service(doc)

    apply_to_leadership_doc(
        rendered_per_dept=rendered,
        rocks_by_dept=rocks,
        doc_id="DOC_X",
        docs_service=service,
        max_sensitivity="leadership",
    )

    body = service.documents.return_value.batchUpdate.call_args.kwargs["body"]
    requests = body["requests"]
    assert len(requests) == 1
    assert "insertText" in requests[0]
    # No deleteContentRange when the span was already empty.
    assert not any("deleteContentRange" in r for r in requests)


def test_apply_fails_loud_when_sentinels_missing(monkeypatch):
    """Patch 3 contract: never insertText append. Must raise + alert."""
    rendered = {"leadership": {"scorecard_rows": [_row("X")]}}
    rocks = {"leadership": {"rocks": [], "projects": []}}
    doc = _doc_without_sentinels()
    service = _make_docs_service(doc)

    captured_alerts = []
    monkeypatch.setattr(
        leadership_doc_writer,
        "emit_failure_alert",
        lambda **kw: captured_alerts.append(kw),
    )

    with pytest.raises(RuntimeError, match="Sentinel pair"):
        apply_to_leadership_doc(
            rendered_per_dept=rendered,
            rocks_by_dept=rocks,
            doc_id="DOC_X",
            docs_service=service,
            max_sensitivity="leadership",
        )

    assert captured_alerts
    assert captured_alerts[0]["surface"] == "leadership_doc"
    # No batchUpdate call — we refused to write anything.
    service.documents.return_value.batchUpdate.assert_not_called()


# ----- Tabbed-doc support ------------------------------------------------- #


def _tabbed_doc(content_between="OLD", tab_id="t.MAY13", with_legacy_body=False):
    """Build a fake Google Docs response in tabbed-doc shape.

    Sentinels live INSIDE one tab (matching the May 13 tab in Recess
    leadership agenda). The legacy `body` field is empty unless explicitly
    requested — Google Docs returns it populated only for non-tabbed
    docs OR for the first tab when called WITHOUT includeTabsContent=True.
    """
    full_text = f"<<KPI_LEADERSHIP_START>>{content_between}<<KPI_LEADERSHIP_END>>"
    tab_body = {
        "content": [
            {
                "paragraph": {
                    "elements": [
                        {
                            "startIndex": 1,
                            "endIndex": 1 + len(full_text),
                            "textRun": {"content": full_text},
                        }
                    ]
                }
            }
        ]
    }
    doc = {
        "tabs": [
            {
                "tabProperties": {"tabId": "t.APR29", "title": "April 29"},
                "documentTab": {
                    "body": {
                        "content": [
                            {
                                "paragraph": {
                                    "elements": [
                                        {
                                            "startIndex": 1,
                                            "endIndex": 22,
                                            "textRun": {
                                                "content": "no sentinels here\n"
                                            },
                                        }
                                    ]
                                }
                            }
                        ]
                    }
                },
            },
            {
                "tabProperties": {"tabId": tab_id, "title": "May 13"},
                "documentTab": {"body": tab_body},
            },
        ]
    }
    if with_legacy_body:
        # Some API responses populate body with the first tab's content for
        # legacy compat. Mimic that.
        doc["body"] = doc["tabs"][0]["documentTab"]["body"]
    return doc


def test_find_sentinel_indexes_locates_sentinels_on_specific_tab():
    """The user's leadership doc places sentinels on the May 13 tab. The
    writer must find them and surface the tab_id so batchUpdate threads it."""
    doc = _tabbed_doc(content_between="placeholder", tab_id="t.MAY13")
    indexes = _find_sentinel_indexes(doc)
    assert indexes is not None
    start_after, end_before, tab_id = indexes
    assert tab_id == "t.MAY13"
    assert end_before - start_after == len("placeholder")


def test_find_sentinel_indexes_skips_unrelated_tabs():
    """The Apr 29 tab has no sentinels; only May 13 does. Walker must skip
    Apr 29 and not return its indexes by mistake."""
    doc = _tabbed_doc(content_between="x", tab_id="t.MAY13")
    indexes = _find_sentinel_indexes(doc)
    assert indexes is not None
    _, _, tab_id = indexes
    assert tab_id == "t.MAY13"
    assert tab_id != "t.APR29"


def test_find_sentinel_indexes_rejects_split_across_tabs():
    """If a typo puts <<START>> in one tab and <<END>> in another, indexes
    are in different namespaces. Walker resets when it sees a tab change
    with a pending start sentinel — refuses to return mismatched pair."""
    doc = {
        "tabs": [
            {
                "tabProperties": {"tabId": "t.A"},
                "documentTab": {
                    "body": {
                        "content": [
                            {
                                "paragraph": {
                                    "elements": [
                                        {
                                            "startIndex": 1,
                                            "textRun": {
                                                "content": "<<KPI_LEADERSHIP_START>>"
                                            },
                                        }
                                    ]
                                }
                            }
                        ]
                    }
                },
            },
            {
                "tabProperties": {"tabId": "t.B"},
                "documentTab": {
                    "body": {
                        "content": [
                            {
                                "paragraph": {
                                    "elements": [
                                        {
                                            "startIndex": 1,
                                            "textRun": {
                                                "content": "<<KPI_LEADERSHIP_END>>"
                                            },
                                        }
                                    ]
                                }
                            }
                        ]
                    }
                },
            },
        ]
    }
    assert _find_sentinel_indexes(doc) is None


def test_apply_to_tabbed_doc_threads_tab_id_in_batch_request():
    """Both deleteContentRange and insertText must include `tabId` so the
    batchUpdate operates in the correct tab namespace."""
    rendered = {"leadership": {"scorecard_rows": [_row("X", display="$200")]}}
    rocks = {"leadership": {"rocks": [], "projects": []}}
    doc = _tabbed_doc(content_between="OLD", tab_id="t.MAY13")
    service = _make_docs_service(doc)

    apply_to_leadership_doc(
        rendered_per_dept=rendered,
        rocks_by_dept=rocks,
        doc_id="DOC_TABBED",
        docs_service=service,
        max_sensitivity="leadership",
    )

    # The get() call must include includeTabsContent=True
    get_call = service.documents.return_value.get.call_args
    assert get_call.kwargs.get("includeTabsContent") is True

    # Both requests carry tabId="t.MAY13"
    body = service.documents.return_value.batchUpdate.call_args.kwargs["body"]
    requests = body["requests"]
    assert len(requests) == 2
    delete_range = requests[0]["deleteContentRange"]["range"]
    insert_loc = requests[1]["insertText"]["location"]
    assert delete_range["tabId"] == "t.MAY13"
    assert insert_loc["tabId"] == "t.MAY13"


def test_apply_to_legacy_body_doc_omits_tab_id():
    """Pre-tab docs (or untabbed docs) have no tabId — the writer must NOT
    include the tabId field, otherwise the API rejects the request."""
    rendered = {"leadership": {"scorecard_rows": [_row("X", display="$1")]}}
    rocks = {"leadership": {"rocks": [], "projects": []}}
    doc = _doc_with_sentinels(content_between="x")
    service = _make_docs_service(doc)

    apply_to_leadership_doc(
        rendered_per_dept=rendered,
        rocks_by_dept=rocks,
        doc_id="DOC_LEGACY",
        docs_service=service,
        max_sensitivity="leadership",
    )

    body = service.documents.return_value.batchUpdate.call_args.kwargs["body"]
    requests = body["requests"]
    delete_range = requests[0]["deleteContentRange"]["range"]
    insert_loc = requests[1]["insertText"]["location"]
    assert "tabId" not in delete_range
    assert "tabId" not in insert_loc


# ----- Sensitivity filter ------------------------------------------------- #


def test_apply_filters_founders_only_at_leadership_max():
    rendered = {
        "leadership": {
            "scorecard_rows": [
                _row("Public", "public", display="$100"),
                _row("LeadershipOnly", "leadership", display="$200"),
                _row("FoundersOnly", "founders_only", display="$300"),
            ]
        }
    }
    rocks = {"leadership": {"rocks": [], "projects": []}}
    doc = _doc_with_sentinels(content_between="x")
    service = _make_docs_service(doc)

    apply_to_leadership_doc(
        rendered_per_dept=rendered,
        rocks_by_dept=rocks,
        doc_id="DOC_X",
        docs_service=service,
        max_sensitivity="leadership",
    )

    body = service.documents.return_value.batchUpdate.call_args.kwargs["body"]
    insert_text = next(
        r["insertText"]["text"] for r in body["requests"] if "insertText" in r
    )
    assert "Public" in insert_text
    assert "LeadershipOnly" in insert_text
    # founders_only is ALWAYS filtered, even at leadership max sensitivity.
    assert "FoundersOnly" not in insert_text
    assert "$300" not in insert_text
