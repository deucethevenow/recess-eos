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


def _row(name, sensitivity="public", display="$1", target_display=None):
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
        target_display=target_display,
        trend_display=None,
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


def test_apply_writes_three_cells_per_row_metric_actual_status():
    """Session 3.6: deck has 5 columns (Metric/Target/Actual/Status/Trend).
    Phase 1 writes 3 of them: col 0 (Metric=display_label), col 2
    (Actual=display), col 3 (Status=status_icon). Cols 1 + 4 left blank
    pending Phase 2 split of target_raw + trend computation.

    Session 3.6 follow-up: the writer now sends ONE batchUpdate per dept
    containing all of that dept's cell writes — reducing API call count
    from ~3*N rows to 1 per dept.
    """
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

    # ONE batchUpdate per dept containing all three cell writes.
    calls = service.presentations.return_value.batchUpdate.call_args_list
    assert len(calls) == 1

    body = calls[0].kwargs.get("body") or calls[0].args[1]
    requests = body["requests"]

    # Cells in the fake fixture are empty → each write is insertText only
    # (no deleteText, which would fail the Slides API on empty cells).
    # 1 row × 3 cells × 1 request each = 3 requests total.
    assert len(requests) == 3
    assert all("insertText" in r for r in requests)
    assert not any("deleteText" in r for r in requests)

    cols_written = sorted(
        r["insertText"]["cellLocation"]["columnIndex"] for r in requests
    )
    # Session 4: writer now writes ALL 5 cols when populated. With
    # target_display=None and trend_display=None (this fixture is a
    # scorecard row), cols 1 and 4 have empty text AND cells are empty,
    # so the skip-empty-cell optimization elides those writes. Only
    # cols 0/2/3 are sent.
    assert cols_written == [0, 2, 3]
    # All inserts at index 0 — preserves the no-re-format invariant.
    for r in requests:
        assert r["insertText"]["insertionIndex"] == 0


def test_apply_clears_stale_cells_beyond_data_rows():
    """Session 4.2 idempotency tail: when a slide has stale content from
    prior runs (or from manually-duplicated source slides), the writer
    clears all non-header cells beyond the current data. Re-runs always
    produce the same end-state regardless of pre-existing content."""
    rendered = {
        "leadership": {
            "scorecard_rows": [_row("OnlyMetric", display="$1")],
            "slide_idx": 0,
        }
    }
    # Build a presentation where rows 2+ have stale content
    populated_table = {
        "tableRows": [
            {"tableCells": [{}, {}, {}, {}, {}]},  # row 0 (header — untouched)
            {"tableCells": [{}, {}, {}, {}, {}]},  # row 1 (gets new write)
            {  # row 2 — STALE content
                "tableCells": [
                    {"text": {"textElements": [{"textRun": {"content": "STALE A"}}]}},
                    {"text": {"textElements": [{"textRun": {"content": "STALE B"}}]}},
                    {},
                    {},
                    {},
                ]
            },
            {  # row 3 — STALE content
                "tableCells": [
                    {"text": {"textElements": [{"textRun": {"content": "STALE C"}}]}},
                    {},
                    {},
                    {},
                    {},
                ]
            },
            {"tableCells": [{}, {}, {}, {}, {}]},  # row 4 — already empty
        ],
        "columns": 5,
    }
    pres = {
        "slides": [
            {
                "objectId": "slide_lead",
                "pageElements": [{"objectId": "tbl_0", "table": populated_table}],
            }
        ]
    }
    service = _make_slides_service(pres)

    apply_via_slides_api(
        rendered_per_dept=rendered,
        max_sensitivity="public",
        slides_service=service,
        presentation_id="DECK_X",
        presentation=pres,
    )

    body = service.presentations.return_value.batchUpdate.call_args.kwargs["body"]
    requests = body["requests"]
    # Clear-tail must emit deleteText for the 3 STALE cells in rows 2-3.
    # No deleteText for row 4 (already empty — skipped).
    delete_requests = [r for r in requests if "deleteText" in r]
    cleared_locations = [
        (
            r["deleteText"]["cellLocation"]["rowIndex"],
            r["deleteText"]["cellLocation"]["columnIndex"],
        )
        for r in delete_requests
    ]
    # Row 2 cols 0+1 stale, row 3 col 0 stale = 3 deletes
    assert (2, 0) in cleared_locations
    assert (2, 1) in cleared_locations
    assert (3, 0) in cleared_locations
    # Row 4 cells were empty — should NOT have a delete
    assert (4, 0) not in cleared_locations


def test_apply_emits_delete_text_for_populated_cells():
    """When existing cell content is non-empty, the writer pairs deleteText
    + insertText to maintain idempotency on re-runs (re-runs MUST replace
    rather than append, otherwise text accumulates per Slides API
    insertText newline semantics)."""
    rendered = {
        "leadership": {
            "scorecard_rows": [_row("Re-run Metric", display="$2.0M")],
            "slide_idx": 0,
        }
    }
    # Build a presentation where row 1 cells already have text — i.e.,
    # the slide has been written to before.
    populated_table = {
        "tableRows": [
            {"tableCells": [{}, {}, {}, {}, {}]},  # row 0 (header — untouched)
            {
                "tableCells": [
                    {"text": {"textElements": [{"textRun": {"content": "OLD"}}]}},
                    {},
                    {"text": {"textElements": [{"textRun": {"content": "OLDV"}}]}},
                    {"text": {"textElements": [{"textRun": {"content": "⚪"}}]}},
                    {},
                ]
            },
            {"tableCells": [{}, {}, {}, {}, {}]},
            {"tableCells": [{}, {}, {}, {}, {}]},
        ],
        "columns": 5,
    }
    pres = {
        "slides": [
            {
                "objectId": "slide_lead",
                "pageElements": [
                    {"objectId": "tbl_0", "table": populated_table}
                ],
            }
        ]
    }
    service = _make_slides_service(pres)

    apply_via_slides_api(
        rendered_per_dept=rendered,
        max_sensitivity="public",
        slides_service=service,
        presentation_id="DECK_X",
        presentation=pres,
    )

    body = service.presentations.return_value.batchUpdate.call_args.kwargs["body"]
    requests = body["requests"]
    # 3 cells, each with deleteText + insertText pair = 6 requests.
    assert len(requests) == 6
    delete_count = sum(1 for r in requests if "deleteText" in r)
    insert_count = sum(1 for r in requests if "insertText" in r)
    assert delete_count == 3
    assert insert_count == 3


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

    # One batchUpdate for the dept (all writes batched).
    assert service.presentations.return_value.batchUpdate.call_count == 1
    body = service.presentations.return_value.batchUpdate.call_args.kwargs["body"]
    requests = body["requests"]
    # Only public row writes (founders_only filtered): 1 row × 3 cells = 3
    # insertText requests (cells empty in fixture, so no deleteText).
    assert len(requests) == 3
    assert all("insertText" in r for r in requests)

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
