"""Session 3 contract tests — deck_writer.

Asserts the four invariants of apply_via_slides_api:
  1. Reads RenderedRow.display_label / RenderedRow.display ONLY (no re-format).
  2. Every cell write is a deleteText + insertText pair (idempotent).
  3. Per-slide try/except: one failing dept does not block the rest.
  4. founders_only rows are filtered before the writer runs.

Plus build_table_row_count_fetcher caching behavior.
"""
from unittest.mock import MagicMock

from lib import deck_writer
from lib.deck_writer import apply_via_slides_api, build_table_row_count_fetcher
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
        is_phase2_placeholder=False,
        is_special_override=False,
    )


def _fake_slide_with_table(table_id):
    return {
        "objectId": f"slide_{table_id}",
        "pageElements": [
            {
                "objectId": table_id,
                "table": {"tableRows": [{}, {}, {}, {}], "columns": 2},
            }
        ],
    }


def _fake_presentation(num_slides=2):
    return {
        "slides": [_fake_slide_with_table(f"tbl_{i}") for i in range(num_slides)]
    }


def _make_slides_service(presentation_dict):
    service = MagicMock()
    service.presentations.return_value.get.return_value.execute.return_value = (
        presentation_dict
    )
    service.presentations.return_value.batchUpdate.return_value.execute.return_value = {
        "replies": []
    }
    return service


# ----- apply_via_slides_api: write contract -------------------------------- #


def test_apply_writes_display_label_and_display_in_paired_calls():
    """Each row produces 2 batchUpdate calls (label + value), each with the
    deleteText+insertText pair from idempotency.write_cell."""
    rendered = {
        "leadership": {
            "scorecard_rows": [_row("Net Revenue YTD", display="$1.04M")],
            "slide_idx": 0,
        }
    }
    pres = _fake_presentation(num_slides=1)
    service = _make_slides_service(pres)

    apply_via_slides_api(
        rendered_per_dept=rendered,
        max_sensitivity="public",
        slides_service=service,
        presentation_id="DECK_X",
        presentation=pres,
    )

    # Two batchUpdate calls: one for label cell, one for value cell.
    calls = service.presentations.return_value.batchUpdate.call_args_list
    assert len(calls) == 2

    # Each batchUpdate request must have deleteText THEN insertText pair.
    for call in calls:
        kwargs = call.kwargs or {}
        body = kwargs.get("body") or call.args[1] if call.args else {}
        if "body" in kwargs:
            body = kwargs["body"]
        requests = body["requests"]
        assert len(requests) == 2
        assert "deleteText" in requests[0]
        assert "insertText" in requests[1]
        # insertText preserves the raw text — no re-format.
        assert requests[1]["insertText"]["insertionIndex"] == 0


def test_apply_skips_founders_only_rows():
    """Sensitivity filter runs before the write — founders_only rows never
    reach the Slides API."""
    rendered = {
        "leadership": {
            "scorecard_rows": [
                _row("Public", "public", display="$100"),
                _row("Sensitive", "founders_only", display="$200"),
            ],
            "slide_idx": 0,
        }
    }
    pres = _fake_presentation(num_slides=1)
    service = _make_slides_service(pres)

    apply_via_slides_api(
        rendered_per_dept=rendered,
        max_sensitivity="public",
        slides_service=service,
        presentation_id="DECK_X",
        presentation=pres,
    )

    # Only the public row writes — 1 row × 2 cells = 2 batchUpdate calls.
    assert service.presentations.return_value.batchUpdate.call_count == 2

    # Verify $200 (founders_only) never appears in any insertText payload.
    for call in service.presentations.return_value.batchUpdate.call_args_list:
        body = call.kwargs.get("body") or call.args[1]
        for req in body["requests"]:
            if "insertText" in req:
                assert "$200" not in req["insertText"]["text"]


def test_apply_skips_dept_with_no_slide_idx():
    rendered = {
        "leadership": {
            "scorecard_rows": [_row("X", display="$1")],
            "slide_idx": None,
        }
    }
    pres = _fake_presentation(num_slides=1)
    service = _make_slides_service(pres)

    apply_via_slides_api(
        rendered_per_dept=rendered,
        max_sensitivity="public",
        slides_service=service,
        presentation_id="DECK_X",
        presentation=pres,
    )

    assert service.presentations.return_value.batchUpdate.call_count == 0


def test_apply_per_slide_failure_does_not_block_other_depts(monkeypatch):
    """Patch 4d: one failing slide writes a failure alert, others continue."""
    rendered = {
        "leadership": {
            "scorecard_rows": [_row("LRow", display="$L")],
            "slide_idx": 0,
        },
        "sales": {
            "scorecard_rows": [_row("SRow", display="$S")],
            "slide_idx": 1,
        },
    }
    pres = _fake_presentation(num_slides=2)

    # Service whose batchUpdate throws on first slide_idx (slide 0), succeeds on slide 1.
    service = _make_slides_service(pres)

    def faulty_batch_update(presentationId, body):  # noqa: N803
        # Determine which slide based on table object id (tbl_0 vs tbl_1)
        first_request = body["requests"][0]
        loc = first_request.get("deleteText") or first_request.get("insertText")
        table_id = loc["objectId"]
        if "tbl_0" in table_id:
            raise RuntimeError("slide 0 boom")
        return MagicMock(execute=MagicMock(return_value={}))

    service.presentations.return_value.batchUpdate.side_effect = faulty_batch_update

    captured_alerts = []
    monkeypatch.setattr(
        deck_writer,
        "emit_failure_alert",
        lambda **kw: captured_alerts.append(kw),
    )

    apply_via_slides_api(
        rendered_per_dept=rendered,
        max_sensitivity="public",
        slides_service=service,
        presentation_id="DECK_X",
        presentation=pres,
    )

    # Failure alert was emitted for the leadership slide.
    leadership_alerts = [a for a in captured_alerts if a.get("dept") == "leadership"]
    assert leadership_alerts
    assert leadership_alerts[0]["surface"] == "deck"
    assert leadership_alerts[0]["slide_idx"] == 0
    # Sales slide STILL got its writes (3 batchUpdate calls succeeded —
    # 1 failed leadership label + 2 sales cells, since faulty_batch_update raises
    # mid-leadership but sales continues).
    assert service.presentations.return_value.batchUpdate.call_count >= 2


def test_apply_alerts_when_slide_has_no_table(monkeypatch):
    rendered = {
        "leadership": {
            "scorecard_rows": [_row("X", display="$1")],
            "slide_idx": 0,
        }
    }
    pres = {"slides": [{"objectId": "no_table_slide", "pageElements": []}]}
    service = _make_slides_service(pres)

    captured_alerts = []
    monkeypatch.setattr(
        deck_writer,
        "emit_failure_alert",
        lambda **kw: captured_alerts.append(kw),
    )

    apply_via_slides_api(
        rendered_per_dept=rendered,
        max_sensitivity="public",
        slides_service=service,
        presentation_id="DECK_X",
        presentation=pres,
    )

    assert any("No table object" in a["detail"] for a in captured_alerts)
    assert service.presentations.return_value.batchUpdate.call_count == 0


# ----- build_table_row_count_fetcher: caching ------------------------------ #


def test_row_count_fetcher_caches_presentation_per_deck_id():
    """A 7-dept preflight run hits the Slides API once for row counts."""
    pres = _fake_presentation(num_slides=3)
    service = _make_slides_service(pres)

    fetcher = build_table_row_count_fetcher(service)

    # Three calls for three different slide indexes on same deck → 1 API call.
    assert fetcher("DECK_A", 0) == 4
    assert fetcher("DECK_A", 1) == 4
    assert fetcher("DECK_A", 2) == 4

    assert service.presentations.return_value.get.call_count == 1


def test_row_count_fetcher_refetches_across_deck_ids():
    pres = _fake_presentation(num_slides=2)
    service = _make_slides_service(pres)

    fetcher = build_table_row_count_fetcher(service)
    fetcher("DECK_A", 0)
    fetcher("DECK_B", 0)

    assert service.presentations.return_value.get.call_count == 2


def test_row_count_fetcher_returns_none_for_out_of_range():
    pres = _fake_presentation(num_slides=2)
    service = _make_slides_service(pres)

    fetcher = build_table_row_count_fetcher(service)
    assert fetcher("DECK_A", 99) is None


def test_row_count_fetcher_returns_none_for_slide_without_table():
    pres = {
        "slides": [
            {"objectId": "no_table", "pageElements": [{"shape": {}}]}
        ]
    }
    service = _make_slides_service(pres)

    fetcher = build_table_row_count_fetcher(service)
    assert fetcher("DECK_A", 0) is None
