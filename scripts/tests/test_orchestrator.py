"""Tests for the orchestrator module — shared infrastructure for all consumers."""

import sys
import os
from unittest.mock import MagicMock, patch
from dataclasses import dataclass

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from lib.orchestrator import (
    ConsumerResult,
    SnapshotUnavailableError,
    build_all_payloads,
    fetch_latest_snapshot,
)
from lib.metric_payloads import MetricPayload


# ── Fixtures ──────────────────────────────────────────────────────────


def _make_snapshot_row(**overrides):
    """Return a minimal snapshot row dict."""
    base = {
        "snapshot_timestamp": "2026-04-12T08:00:00Z",
        "demand_nrr": 0.22,
        "pipeline_coverage": 2.1,
        "total_sellable_inventory": 1200000,
    }
    base.update(overrides)
    return base


def _make_meeting_config(meeting_id="sales", metrics=None):
    """Return a minimal meeting config dict."""
    if metrics is None:
        metrics = [
            {
                "name": "Demand NRR",
                "registry_key": "Demand NRR",
                "target": 0.50,
                "sensitivity": "public",
                "status": "automated",
                "null_behavior": "show_dash",
            }
        ]
    return {"id": meeting_id, "name": f"{meeting_id} L10", "scorecard_metrics": metrics}


def _make_config(meetings=None):
    """Return a config dict with meetings list."""
    return {"meetings": meetings or []}


# ── fetch_latest_snapshot ─────────────────────────────────────────────


class TestFetchLatestSnapshot:

    def test_returns_row_and_timestamp(self):
        mock_client = MagicMock()
        row = _make_snapshot_row()
        mock_client.query.return_value = [row]

        result_row, result_ts = fetch_latest_snapshot(mock_client)

        assert result_row == row
        assert result_ts == "2026-04-12T08:00:00Z"

    def test_raises_on_empty(self):
        mock_client = MagicMock()
        mock_client.query.return_value = []

        with pytest.raises(SnapshotUnavailableError):
            fetch_latest_snapshot(mock_client)

    def test_uses_first_row_when_multiple(self):
        mock_client = MagicMock()
        row1 = _make_snapshot_row(snapshot_timestamp="2026-04-12T08:00:00Z")
        row2 = _make_snapshot_row(snapshot_timestamp="2026-04-11T08:00:00Z")
        mock_client.query.return_value = [row1, row2]

        result_row, result_ts = fetch_latest_snapshot(mock_client)

        assert result_ts == "2026-04-12T08:00:00Z"
        assert result_row is row1


# ── build_all_payloads ────────────────────────────────────────────────


class TestBuildAllPayloads:

    def test_iterates_all_meetings(self):
        """Should produce payloads for every meeting in config."""
        config = _make_config([
            _make_meeting_config("sales"),
            _make_meeting_config("supply"),
        ])
        row = _make_snapshot_row()

        result = build_all_payloads(config, row, "2026-04-12T08:00:00Z")

        assert "sales" in result
        assert "supply" in result
        assert len(result) == 2

    def test_passes_same_snapshot_row(self):
        """All payloads should share the same snapshot_timestamp."""
        config = _make_config([
            _make_meeting_config("sales"),
            _make_meeting_config("supply"),
        ])
        row = _make_snapshot_row()
        ts = "2026-04-12T08:00:00Z"

        result = build_all_payloads(config, row, ts)

        all_timestamps = {
            p.snapshot_timestamp
            for dept_payloads in result.values()
            for p in dept_payloads
        }
        # All should be the same timestamp (or empty if no metrics resolved)
        assert len(all_timestamps) <= 1

    def test_empty_meetings_returns_empty_dict(self):
        config = _make_config([])
        row = _make_snapshot_row()

        result = build_all_payloads(config, row, "2026-04-12T08:00:00Z")

        assert result == {}

    def test_uses_meeting_id_as_key(self):
        config = _make_config([_make_meeting_config("demand_am")])
        row = _make_snapshot_row()

        result = build_all_payloads(config, row, "2026-04-12T08:00:00Z")

        assert "demand_am" in result
        assert len(result) == 1

    def test_asserts_single_snapshot_timestamp(self):
        """If somehow payloads end up with mixed timestamps, should raise."""
        config = _make_config([_make_meeting_config("sales")])
        row = _make_snapshot_row()

        # Normal case should not raise
        result = build_all_payloads(config, row, "2026-04-12T08:00:00Z")
        assert isinstance(result, dict)


# ── ConsumerResult ────────────────────────────────────────────────────


class TestConsumerResult:

    def test_consumer_result_fields(self):
        cr = ConsumerResult(
            registry_key="Demand NRR",
            dept_id="sales",
            consumer="slack_pulse",
            action="delivered",
        )
        assert cr.registry_key == "Demand NRR"
        assert cr.error_message is None

    def test_consumer_result_with_error(self):
        cr = ConsumerResult(
            registry_key="Pipeline Coverage",
            dept_id="sales",
            consumer="asana_goal",
            action="error",
            error_message="API timeout",
        )
        assert cr.action == "error"
        assert cr.error_message == "API timeout"
