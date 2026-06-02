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


# ----- "Last refreshed:" subtitle update ----------------------------------- #


def test_format_last_refreshed_renders_et_string():
    from datetime import datetime
    from zoneinfo import ZoneInfo

    ts = datetime(2026, 5, 19, 9, 47, tzinfo=ZoneInfo("America/New_York"))
    s = deck_writer._format_last_refreshed(ts)
    assert s == (
        "Last refreshed: 2026-05-19 09:47 ET"
        "  ·  Auto-updated by /monday-kpi-update"
    )


def test_format_last_refreshed_converts_utc_to_et():
    from datetime import datetime, timezone

    # 2026-05-19 13:47 UTC == 09:47 ET (EDT, May → UTC-4)
    ts = datetime(2026, 5, 19, 13, 47, tzinfo=timezone.utc)
    s = deck_writer._format_last_refreshed(ts)
    assert "2026-05-19 09:47 ET" in s


def test_find_last_refreshed_element_finds_subtitle():
    slide = {
        "pageElements": [
            {
                "objectId": "title_shape",
                "shape": {
                    "text": {
                        "textElements": [
                            {"textRun": {"content": "Engineering · Auto-Updated Scorecard"}}
                        ]
                    }
                },
            },
            {
                "objectId": "subtitle_shape",
                "shape": {
                    "text": {
                        "textElements": [
                            {
                                "textRun": {
                                    "content": "Last refreshed: 2026-05-01 13:06 ET  ·  Source: BigQuery + leadership pre-read"
                                }
                            }
                        ]
                    }
                },
            },
        ]
    }
    el = deck_writer._find_last_refreshed_element(slide)
    assert el is not None
    assert el["objectId"] == "subtitle_shape"


def test_find_last_refreshed_element_returns_none_when_absent():
    slide = {
        "pageElements": [
            {
                "objectId": "title_shape",
                "shape": {
                    "text": {
                        "textElements": [
                            {"textRun": {"content": "Sales · Auto-Updated Scorecard"}}
                        ]
                    }
                },
            }
        ]
    }
    assert deck_writer._find_last_refreshed_element(slide) is None


def test_apply_via_slides_api_does_not_touch_subtitle():
    """Subtitle refresh is owned by refresh_last_refreshed_subtitles_deckwide,
    not by apply_via_slides_api. The data writer keeps a single concern —
    table cells — so slides without a dept payload still get their subtitle
    refreshed by the deck-wide pass."""
    rendered = {
        "leadership": {
            "scorecard_rows": [_row("Take Rate", display="47%")],
            "slide_idx": 0,
        }
    }
    subtitle_shape = {
        "objectId": "subtitle_shape",
        "shape": {
            "text": {
                "textElements": [
                    {
                        "textRun": {
                            "content": "Last refreshed: 2026-05-01 13:06 ET  ·  Source: BigQuery + leadership pre-read"
                        }
                    }
                ]
            }
        },
    }
    table_elem = {
        "objectId": "tbl_0",
        "table": {"tableRows": [{}, {}], "columns": 5},
    }
    pres = {
        "slides": [
            {
                "objectId": "slide_lead",
                "pageElements": [subtitle_shape, table_elem],
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
    subtitle_requests = [
        r for r in requests
        if ("insertText" in r and r["insertText"].get("objectId") == "subtitle_shape")
        or ("deleteText" in r and r["deleteText"].get("objectId") == "subtitle_shape")
    ]
    assert subtitle_requests == []


# ----- refresh_last_refreshed_subtitles_deckwide ----------------------------- #


def _subtitle_shape(obj_id, old_text="Last refreshed: 2026-05-01 13:06 ET  ·  Source: BigQuery + leadership pre-read"):
    return {
        "objectId": obj_id,
        "shape": {"text": {"textElements": [{"textRun": {"content": old_text}}]}},
    }


def test_refresh_subtitles_updates_every_matching_slide():
    pres = {
        "slides": [
            {"pageElements": [_subtitle_shape("sub_eng"), {"table": {}}]},
            {"pageElements": [{"shape": {"text": {"textElements": []}}}]},  # no subtitle
            {"pageElements": [_subtitle_shape("sub_sales"), {"table": {}}]},
        ]
    }
    service = _make_slides_service(pres)
    n = deck_writer.refresh_last_refreshed_subtitles_deckwide(
        slides_service=service, presentation_id="DECK_X", presentation=pres
    )
    assert n == 2

    body = service.presentations.return_value.batchUpdate.call_args.kwargs["body"]
    requests = body["requests"]
    updated_ids = {
        r["insertText"]["objectId"] for r in requests if "insertText" in r
    }
    assert updated_ids == {"sub_eng", "sub_sales"}
    # Today's date string in the inserted text — confirms the refresh path
    # produces the canonical format from _format_last_refreshed().
    inserted_texts = [
        r["insertText"]["text"] for r in requests if "insertText" in r
    ]
    for txt in inserted_texts:
        assert txt.startswith("Last refreshed:")
        assert txt.endswith("·  Auto-updated by /monday-kpi-update")
        assert "2026-05-01" not in txt


def test_refresh_subtitles_no_op_when_deck_has_no_subtitles():
    pres = {
        "slides": [
            {"pageElements": [{"shape": {"text": {"textElements": []}}}]},
            {"pageElements": [{"table": {}}]},
        ]
    }
    service = _make_slides_service(pres)
    n = deck_writer.refresh_last_refreshed_subtitles_deckwide(
        slides_service=service, presentation_id="DECK_X", presentation=pres
    )
    assert n == 0
    # No batchUpdate fired — empty request list is short-circuited.
    service.presentations.return_value.batchUpdate.assert_not_called()


def test_refresh_subtitles_emits_single_batch_update():
    """All N subtitle updates land in ONE batchUpdate call, not N calls."""
    pres = {
        "slides": [
            {"pageElements": [_subtitle_shape(f"sub_{i}")]} for i in range(5)
        ]
    }
    service = _make_slides_service(pres)
    deck_writer.refresh_last_refreshed_subtitles_deckwide(
        slides_service=service, presentation_id="DECK_X", presentation=pres
    )
    assert service.presentations.return_value.batchUpdate.call_count == 1


# ----- build_table_row_padder ----------------------------------------------- #


def _slide_with_table_having_n_rows(table_id, n_rows):
    return {
        "objectId": f"slide_{table_id}",
        "pageElements": [
            {
                "objectId": table_id,
                "table": {"tableRows": [{} for _ in range(n_rows)], "columns": 5},
            }
        ],
    }


def test_table_row_padder_inserts_rows_below_last_row():
    pres = {"slides": [_slide_with_table_having_n_rows("tbl_a", 3)]}
    service = _make_slides_service(pres)
    padder = deck_writer.build_table_row_padder(service)

    result = padder("DECK_X", 0, 2)

    assert result is True
    body = service.presentations.return_value.batchUpdate.call_args.kwargs["body"]
    reqs = body["requests"]
    assert len(reqs) == 1
    insert = reqs[0]["insertTableRows"]
    assert insert["tableObjectId"] == "tbl_a"
    assert insert["cellLocation"] == {"rowIndex": 2, "columnIndex": 0}  # last existing row
    assert insert["insertBelow"] is True
    assert insert["number"] == 2


def test_table_row_padder_returns_false_for_out_of_range_slide():
    pres = {"slides": [_slide_with_table_having_n_rows("tbl_a", 3)]}
    service = _make_slides_service(pres)
    padder = deck_writer.build_table_row_padder(service)

    result = padder("DECK_X", 99, 1)

    assert result is False
    service.presentations.return_value.batchUpdate.assert_not_called()


def test_table_row_padder_returns_false_when_slide_has_no_table():
    pres = {"slides": [{"objectId": "no_tbl_slide", "pageElements": [{"shape": {}}]}]}
    service = _make_slides_service(pres)
    padder = deck_writer.build_table_row_padder(service)

    result = padder("DECK_X", 0, 1)

    assert result is False
    service.presentations.return_value.batchUpdate.assert_not_called()


def test_table_row_padder_noop_when_n_to_add_is_zero():
    pres = {"slides": [_slide_with_table_having_n_rows("tbl_a", 3)]}
    service = _make_slides_service(pres)
    padder = deck_writer.build_table_row_padder(service)

    result = padder("DECK_X", 0, 0)

    assert result is True
    # Should NOT call any Slides API method — n_to_add=0 is a definitional no-op.
    service.presentations.return_value.get.assert_not_called()
    service.presentations.return_value.batchUpdate.assert_not_called()
