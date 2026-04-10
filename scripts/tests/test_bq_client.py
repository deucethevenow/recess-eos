"""Tests for the BigQuery client wrapper."""
from unittest.mock import MagicMock, patch

import pytest

from lib.bq_client import RecessOSBQClient


@pytest.fixture
def mock_bq():
    with patch("lib.bq_client.bigquery.Client") as mock_client:
        yield mock_client


class TestRecessOSBQClient:
    def test_initializes_with_project(self, mock_bq):
        client = RecessOSBQClient(project_id="test-project", dataset="test_dataset")
        mock_bq.assert_called_once_with(project="test-project")
        assert client.dataset == "test_dataset"

    def test_full_table_id(self, mock_bq):
        client = RecessOSBQClient(project_id="p", dataset="d")
        assert client.full_table_id("eos_rocks") == "p.d.eos_rocks"


class TestLoadSnapshot:
    def test_load_snapshot_uses_write_truncate(self, mock_bq):
        """Snapshot tables must use WRITE_TRUNCATE for atomic replacement."""
        client = RecessOSBQClient(project_id="p", dataset="d")
        mock_job = MagicMock()
        mock_job.result.return_value = None
        client.bq.load_table_from_json.return_value = mock_job

        rows = [{"asana_project_id": "1"}, {"asana_project_id": "2"}]
        n = client.load_snapshot("eos_projects", rows)

        # Verify load_table_from_json was called with WRITE_TRUNCATE
        call_args = client.bq.load_table_from_json.call_args
        job_config = call_args.kwargs.get("job_config") or call_args.args[2]
        assert job_config.write_disposition == "WRITE_TRUNCATE"
        assert n == 2

    def test_load_snapshot_empty_rows_truncates_table(self, mock_bq):
        """Loading [] into a snapshot table must still TRUNCATE — empty is a valid state."""
        client = RecessOSBQClient(project_id="p", dataset="d")
        mock_job = MagicMock()
        mock_job.result.return_value = None
        mock_job.output_rows = 0
        client.bq.load_table_from_json.return_value = mock_job

        n = client.load_snapshot("eos_projects", [])
        # Must still dispatch a load job with WRITE_TRUNCATE to clear the table
        client.bq.load_table_from_json.assert_called_once()
        assert n == 0

    def test_load_snapshot_raises_on_job_error(self, mock_bq):
        client = RecessOSBQClient(project_id="p", dataset="d")
        mock_job = MagicMock()
        mock_job.result.side_effect = Exception("load job failed")
        client.bq.load_table_from_json.return_value = mock_job

        with pytest.raises(Exception, match="load job failed"):
            client.load_snapshot("eos_projects", [{"asana_project_id": "1"}])


class TestMergeEvents:
    def test_merge_events_creates_staging_and_merges(self, mock_bq):
        """Event tables must load to per-run staging then MERGE WHEN NOT MATCHED THEN INSERT only."""
        client = RecessOSBQClient(project_id="p", dataset="d")
        # Mock get_table to return a table with an empty schema list
        # (LoadJobConfig.schema setter requires a Sequence, not a MagicMock)
        mock_main_table = MagicMock()
        mock_main_table.schema = []
        client.bq.get_table.return_value = mock_main_table

        mock_load_job = MagicMock()
        mock_load_job.result.return_value = None
        mock_load_job.output_rows = 2
        client.bq.load_table_from_json.return_value = mock_load_job

        mock_query_job = MagicMock()
        mock_query_job.result.return_value = None
        mock_query_job.num_dml_affected_rows = 2
        client.bq.query.return_value = mock_query_job

        rows = [
            {"status_update_gid": "a1", "parent_gid": "p1", "text": "hi"},
            {"status_update_gid": "a2", "parent_gid": "p1", "text": "yo"},
        ]
        n = client.merge_events(
            "eos_status_updates",
            rows,
            natural_key_columns=["status_update_gid"],
            run_id="test-run-123",
        )

        # Verify get_table was called to fetch schema from main table
        client.bq.get_table.assert_called_once()

        # Verify staging table name includes run_id (dashes replaced with underscores for BQ)
        load_call = client.bq.load_table_from_json.call_args
        assert "test_run_123" in str(load_call)

        # Verify the MERGE SQL contains "WHEN NOT MATCHED THEN INSERT"
        # and does NOT contain "WHEN MATCHED" (immutable rule)
        merge_sql = client.bq.query.call_args.args[0]
        assert "MERGE INTO" in merge_sql
        assert "WHEN NOT MATCHED THEN INSERT" in merge_sql
        assert "WHEN MATCHED" not in merge_sql, (
            "Event tables are immutable — MERGE must NOT have a WHEN MATCHED clause"
        )
        assert n == 2

    def test_merge_events_composite_natural_key(self, mock_bq):
        """Composite natural keys (e.g. eos_goal_metric_history) are joined with AND."""
        client = RecessOSBQClient(project_id="p", dataset="d")
        mock_main_table = MagicMock()
        mock_main_table.schema = []
        client.bq.get_table.return_value = mock_main_table

        mock_load_job = MagicMock()
        mock_load_job.result.return_value = None
        mock_load_job.output_rows = 1
        client.bq.load_table_from_json.return_value = mock_load_job

        mock_query_job = MagicMock()
        mock_query_job.result.return_value = None
        mock_query_job.num_dml_affected_rows = 1
        client.bq.query.return_value = mock_query_job

        client.merge_events(
            "eos_goal_metric_history",
            [{"asana_goal_id": "g1", "pushed_at": "2026-04-10T08:00:00Z", "pushed_value": 42.0}],
            natural_key_columns=["asana_goal_id", "pushed_at"],
            run_id="run-xyz",
        )

        merge_sql = client.bq.query.call_args.args[0]
        assert "T.asana_goal_id = S.asana_goal_id" in merge_sql
        assert "T.pushed_at = S.pushed_at" in merge_sql
        assert " AND " in merge_sql  # composite join

    def test_merge_events_empty_rows_is_noop(self, mock_bq):
        """Empty event batch must NOT hit BQ at all — event tables are additive."""
        client = RecessOSBQClient(project_id="p", dataset="d")
        n = client.merge_events(
            "eos_status_updates",
            [],
            natural_key_columns=["status_update_gid"],
            run_id="test",
        )
        assert n == 0
        client.bq.load_table_from_json.assert_not_called()
        client.bq.query.assert_not_called()


class TestQuery:
    def test_query_returns_rows_as_dicts(self, mock_bq):
        client = RecessOSBQClient(project_id="p", dataset="d")
        mock_row = MagicMock()
        mock_row.items.return_value = [("a", 1), ("b", "hi")]
        client.bq.query.return_value.result.return_value = [mock_row]

        result = client.query("SELECT 1")
        assert result == [{"a": 1, "b": "hi"}]
