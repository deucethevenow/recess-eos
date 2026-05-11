"""Session 3 end-to-end smoke test — main() against fakes.

Wires fake Slides + fake Slack + fake Docs services together and runs main()
end-to-end. Asserts:
  1. With skip_deck=False, fetch_presentation/fetch_table_row_count/slides_service
     ARE all required (ValueError raised early).
  2. With skip_deck=True, the deck step is bypassed and Slack still posts.
  3. Sensitivity gate is honored (input_fn = lambda _: "y" proceeds; "n" aborts).
  4. The whole pipeline completes without unhandled exceptions on a sane fixture.
"""
from unittest.mock import MagicMock

import pytest


# ----- NIT-3: required keyword args --------------------------------------- #


def test_main_raises_when_skip_deck_false_and_callbacks_missing():
    """A future caller forgetting fetch_presentation must fail at signature
    validation, not at preflight with N confusing 'no slide_idx' errors."""
    import monday_kpi_update

    with pytest.raises(ValueError, match="skip_deck=False requires"):
        monday_kpi_update.main(
            skip_deck=False,
            fetch_presentation=None,
            input_fn=lambda _: "y",
        )


def test_main_raises_when_leadership_doc_requested_without_service():
    import monday_kpi_update

    with pytest.raises(ValueError, match="include_leadership_doc=True"):
        monday_kpi_update.main(
            skip_deck=True,
            include_leadership_doc=True,
            leadership_doc_id=None,
            docs_service=None,
            input_fn=lambda _: "y",
        )


# ----- skip_deck=True path: Slack still posts ----------------------------- #


def test_main_skip_deck_true_still_posts_slack(monkeypatch):
    """skip_deck=True bypasses Slides API entirely; Slack still posts via the
    injected post_fn. Preflight does not surface 'no slide_idx' errors."""
    import monday_kpi_update

    # Stub data layer dependencies
    monkeypatch.setattr(
        monday_kpi_update,
        "get_company_metrics",
        lambda: {},
    )
    monkeypatch.setattr(
        monday_kpi_update,
        "get_rock_project_progress",
        lambda: {
            "available": True,
            "rocks": [],
            "projects": [],
        },
    )
    # One dept with one metric so render loop has something to do.
    monkeypatch.setattr(
        monday_kpi_update,
        "get_scorecard_metrics_for_dept",
        lambda dept_id: (
            [{"key": "Net Revenue YTD", "scorecard_status": "needs_build"}]
            if dept_id == "leadership"
            else []
        ),
    )

    # Slack post: fake post_fn skips real httpx
    post_calls = []

    def fake_post(*, channel_id, blocks):
        post_calls.append((channel_id, blocks))
        return "TS_E2E"

    # Firestore: marker absent → write happens
    fake_db = MagicMock()
    fake_doc_ref = fake_db.collection.return_value.document.return_value
    fake_doc_ref.get.return_value.exists = False
    fake_doc_ref.get.return_value.to_dict.return_value = {}

    fake_firestore = MagicMock()
    fake_firestore.SERVER_TIMESTAMP = "SENTINEL"
    monkeypatch.setitem(
        __import__("sys").modules,
        "google.cloud",
        MagicMock(firestore=fake_firestore),
    )
    monkeypatch.setitem(
        __import__("sys").modules, "google.cloud.firestore", fake_firestore
    )

    monday_kpi_update.main(
        skip_deck=True,
        skip_slack=False,
        include_leadership_doc=False,
        slack_post_fn=fake_post,
        firestore_client=fake_db,
        input_fn=lambda _: "y",
    )

    assert len(post_calls) == 1
    # Default channel is the Phase 11 verify channel.
    assert post_calls[0][0] == monday_kpi_update.VERIFY_SLACK_CHANNEL


def test_main_aborts_at_sensitivity_gate_on_n_response(monkeypatch):
    """Patch 2: SystemExit when operator answers anything other than 'y'."""
    import monday_kpi_update

    monkeypatch.setattr(
        monday_kpi_update,
        "get_company_metrics",
        lambda: {},
    )
    monkeypatch.setattr(
        monday_kpi_update,
        "get_rock_project_progress",
        lambda: {"available": True, "rocks": [], "projects": []},
    )
    monkeypatch.setattr(
        monday_kpi_update,
        "get_scorecard_metrics_for_dept",
        lambda dept_id: (
            [{"key": "X", "scorecard_status": "needs_build"}]
            if dept_id == "leadership"
            else []
        ),
    )

    with pytest.raises(SystemExit):
        monday_kpi_update.main(
            skip_deck=True,
            skip_slack=True,
            input_fn=lambda _: "n",
        )


# ----- skip_deck=False with fakes: full path ------------------------------ #


def test_main_skip_deck_false_with_fakes_runs_end_to_end(monkeypatch):
    """skip_deck=False requires Slides API bindings — provide fakes, verify
    that resolve_dept_slide_map + preflight + deck writer all dispatch."""
    import monday_kpi_update

    monkeypatch.setattr(
        monday_kpi_update,
        "get_company_metrics",
        lambda: {},
    )
    monkeypatch.setattr(
        monday_kpi_update,
        "get_rock_project_progress",
        lambda: {"available": True, "rocks": [], "projects": []},
    )
    monkeypatch.setattr(
        monday_kpi_update,
        "get_scorecard_metrics_for_dept",
        lambda dept_id: (
            [{"key": "Y", "scorecard_status": "needs_build"}]
            if dept_id == "sales"
            else []
        ),
    )

    # Fake Slides presentation: sales slide at index 0 with a 4-row table.
    # (Session 4.1: Leadership was removed from DEPT_TITLE_MAP — fixture must
    # use a dept that's still in the map so the deck dispatch fires.)
    fake_pres = {
        "slides": [
            {
                "objectId": "slide_sales",
                "pageElements": [
                    {
                        "objectId": "title_shape",
                        "shape": {
                            "placeholder": {"type": "TITLE"},
                            "text": {
                                "textElements": [
                                    {
                                        "textRun": {
                                            "content": "Sales · Auto-Updated Scorecard"
                                        }
                                    }
                                ]
                            },
                        },
                    },
                    {
                        "objectId": "tbl_sales",
                        "table": {"tableRows": [{}, {}, {}, {}], "columns": 2},
                    },
                ],
            }
        ]
    }

    fake_slides_service = MagicMock()
    fake_slides_service.presentations.return_value.get.return_value.execute.return_value = (
        fake_pres
    )
    fake_slides_service.presentations.return_value.batchUpdate.return_value.execute.return_value = {}

    def fetch_presentation(deck_id):
        return fake_pres

    def fetch_table_row_count(deck_id, slide_idx):
        slides = fake_pres.get("slides", [])
        if slide_idx >= len(slides):
            return None
        for el in slides[slide_idx].get("pageElements", []):
            if "table" in el:
                return len(el["table"]["tableRows"])
        return None

    # Slack
    post_calls = []

    def fake_post(*, channel_id, blocks):
        post_calls.append((channel_id, blocks))
        return "TS_E2E"

    fake_db = MagicMock()
    fake_doc_ref = fake_db.collection.return_value.document.return_value
    fake_doc_ref.get.return_value.exists = False
    fake_doc_ref.get.return_value.to_dict.return_value = {}

    fake_firestore = MagicMock()
    fake_firestore.SERVER_TIMESTAMP = "SENTINEL"
    monkeypatch.setitem(
        __import__("sys").modules,
        "google.cloud",
        MagicMock(firestore=fake_firestore),
    )
    monkeypatch.setitem(
        __import__("sys").modules, "google.cloud.firestore", fake_firestore
    )

    rendered = monday_kpi_update.main(
        skip_deck=False,
        skip_rocks_deck=True,  # rocks slide isn't in fixture; not testing rocks here
        skip_slack=False,
        include_leadership_doc=False,
        fetch_presentation=fetch_presentation,
        fetch_table_row_count=fetch_table_row_count,
        slides_service=fake_slides_service,
        slack_post_fn=fake_post,
        firestore_client=fake_db,
        input_fn=lambda _: "y",
    )

    assert "sales" in rendered
    # Deck writes happened — at least one batchUpdate to slides
    assert fake_slides_service.presentations.return_value.batchUpdate.called
    # Slack posted
    assert len(post_calls) == 1
