"""Tests for sync_projects logic."""
import json
from datetime import datetime
from unittest.mock import MagicMock

from lib.sync_projects import asana_project_to_bq_row, sync_projects_to_bq


def test_converts_asana_project_to_bq_row():
    asana_project = {
        "gid": "1234567890",
        "name": "Test Project",
        "owner": {"name": "Deuce Thevenow", "email": "deuce@recess.is"},
        "due_on": "2026-06-01",
        "modified_at": "2026-04-06T10:00:00.000Z",
        "custom_fields": [
            {"gid": "cf_11", "name": "Project Type", "text_value": "rock"},
            {"gid": "cf_22", "name": "Linked Rock Goal", "text_value": "1213964742972565"},
        ],
    }
    row = asana_project_to_bq_row(asana_project)
    assert row["asana_project_id"] == "1234567890"
    assert row["name"] == "Test Project"
    assert row["owner_email"] == "deuce@recess.is"
    assert row["project_type"] == "rock"
    assert row["linked_rock_goal_id"] == "1213964742972565"
    assert "synced_at" in row


def test_custom_fields_json_has_both_name_and_gid_views():
    """Dual-format: fields_by_name + fields_by_gid for rename safety."""
    asana_project = {
        "gid": "1",
        "name": "P",
        "owner": None,
        "custom_fields": [
            {"gid": "cf_99", "name": "Project Type", "text_value": "rock"},
            {"gid": "cf_88", "name": "Tier", "number_value": 1},
        ],
    }
    row = asana_project_to_bq_row(asana_project)
    assert "custom_fields_json" in row
    parsed = json.loads(row["custom_fields_json"])
    assert "fields_by_name" in parsed
    assert "fields_by_gid" in parsed
    assert parsed["fields_by_name"]["Project Type"] == "rock"
    assert parsed["fields_by_gid"]["cf_99"] == "rock"
    assert parsed["fields_by_name"]["Tier"] == 1
    assert parsed["fields_by_gid"]["cf_88"] == 1


def test_handles_missing_custom_fields():
    asana_project = {
        "gid": "999",
        "name": "Bare Project",
        "owner": None,
        "custom_fields": [],
    }
    row = asana_project_to_bq_row(asana_project)
    assert row["asana_project_id"] == "999"
    assert row["project_type"] is None
    assert row["linked_rock_goal_id"] is None
    assert row["owner_email"] is None
    parsed = json.loads(row["custom_fields_json"])
    assert parsed == {"fields_by_name": {}, "fields_by_gid": {}}


def test_sync_projects_uses_load_snapshot_not_insert_rows():
    """Critical: snapshot tables MUST use load_snapshot, not insert_rows."""
    asana = MagicMock()
    asana.list_projects_in_portfolio.return_value = [
        {"gid": "1", "name": "A", "owner": None, "custom_fields": []},
        {"gid": "2", "name": "B", "owner": None, "custom_fields": []},
    ]
    bq = MagicMock()
    bq.load_snapshot.return_value = 2

    n = sync_projects_to_bq(asana, bq, portfolio_gid="port1")
    assert n == 2
    bq.load_snapshot.assert_called_once()
    # Verify it's load_snapshot, not insert_rows or merge_events
    assert not bq.insert_rows.called
    assert not bq.merge_events.called
    # Verify the table name passed is 'eos_projects'
    assert bq.load_snapshot.call_args.args[0] == "eos_projects"
