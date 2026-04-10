"""Tests for the @sync_instrumented decorator."""
from unittest.mock import MagicMock

import pytest

from lib.instrumentation import SyncRunTracker, sync_instrumented


class TestSyncRunTracker:
    def test_generates_unique_run_id(self):
        t1 = SyncRunTracker(bq_client=MagicMock(), cron_trigger="test")
        t2 = SyncRunTracker(bq_client=MagicMock(), cron_trigger="test")
        assert t1.run_id != t2.run_id
        assert len(t1.run_id) >= 32  # UUID4 hex form

    def test_records_table_write(self):
        bq = MagicMock()
        t = SyncRunTracker(bq_client=bq, cron_trigger="test")
        t.start()
        t.record_table_write("eos_projects", 42)
        t.finish(success=True)

        # start() no longer writes to BQ (would block finish's ALL row via INSERT-only MERGE).
        # Exactly one merge_events call at finish(), batching per-table + ALL rows.
        assert bq.merge_events.call_count == 1
        rows = bq.merge_events.call_args.kwargs.get("rows") or bq.merge_events.call_args.args[1]
        table_names = [r["table_name"] for r in rows]
        assert "eos_projects" in table_names
        assert "ALL" in table_names
        # Verify the ALL row has the correct final status and row count
        all_row = [r for r in rows if r["table_name"] == "ALL"][0]
        assert all_row["status"] == "success"
        assert all_row["row_count"] == 42

    def test_captures_error_on_failure(self):
        bq = MagicMock()
        t = SyncRunTracker(bq_client=bq, cron_trigger="test")
        t.start()
        t.finish(success=False, error_message="Asana API 429 rate limit")

        # Find the 'ALL' finish call and verify status=failed
        finish_call_rows = None
        for call in bq.merge_events.call_args_list:
            rows = call.kwargs.get("rows") or call.args[1]
            for row in rows:
                if row.get("table_name") == "ALL" and row.get("status") == "failed":
                    finish_call_rows = row
        assert finish_call_rows is not None
        assert "rate limit" in finish_call_rows["error_message"]


class TestSyncInstrumentedDecorator:
    def test_decorator_wraps_function(self):
        bq = MagicMock()

        @sync_instrumented(cron_trigger="test")
        def my_sync(ctx):
            ctx.obj["instrumentation"].record_table_write("eos_projects", 10)
            return "ok"

        ctx = MagicMock()
        ctx.obj = {"bq_client": bq}
        result = my_sync(ctx)
        assert result == "ok"
        # SyncRunTracker should have been instantiated + finished
        assert bq.merge_events.called

    def test_decorator_captures_exception(self):
        bq = MagicMock()

        @sync_instrumented(cron_trigger="test")
        def failing_sync(ctx):
            raise ValueError("something broke")

        ctx = MagicMock()
        ctx.obj = {"bq_client": bq}
        with pytest.raises(ValueError, match="something broke"):
            failing_sync(ctx)

        # Must have written a status=failed row before re-raising
        failed_row_found = False
        for call in bq.merge_events.call_args_list:
            rows = call.kwargs.get("rows") or call.args[1]
            for row in rows:
                if row.get("status") == "failed" and "something broke" in (row.get("error_message") or ""):
                    failed_row_found = True
        assert failed_row_found, "Decorator must write a failed row before re-raising"
