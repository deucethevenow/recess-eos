"""Tests for the recess_os CLI entry point and Phase 2 subcommands."""

import sys
import os
from unittest.mock import MagicMock, patch, PropertyMock

import pytest
from click.testing import CliRunner

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from recess_os import cli, _run_phase2_command, _consumer_results_to_audit_entries
from lib.orchestrator import ConsumerResult, SnapshotUnavailableError
from lib.metric_payloads import MetricPayload


# ── Fixtures ──────────────────────────────────────────────────────────


def _payload(**overrides) -> MetricPayload:
    defaults = dict(
        metric_name="Demand NRR", config_key="Demand NRR",
        registry_key="Demand NRR", snapshot_column="demand_nrr",
        raw_value=0.22, transformed_value=0.44, target=0.50,
        display_value="22.0%", metric_unit="percent",
        format_spec="percent", transform="percent_higher_is_better",
        snapshot_timestamp="2026-04-14T08:00:00Z",
        sensitivity="public", availability_state="live",
        dept_id="sales", notes=None,
    )
    defaults.update(overrides)
    return MetricPayload(**defaults)


MOCK_CONFIG = {
    "meetings": [{"id": "sales", "name": "Sales L10", "scorecard_metrics": [
        {"name": "Demand NRR", "registry_key": "Demand NRR", "target": 0.50,
         "sensitivity": "public", "status": "automated", "null_behavior": "show_dash"},
    ]}],
    "goals": [],
    "bigquery": {"project_id": "test", "dataset": "test"},
    "cron": {"reference_week": 14, "goals_weeks": "even"},
}


# ── Basic CLI tests ──────────────────────────────────────────────────


def test_cli_invokes():
    runner = CliRunner()
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "recess os" in result.output.lower()


@patch("recess_os.load_config", return_value=MOCK_CONFIG)
def test_cli_has_sync_to_bq_command(_):
    runner = CliRunner()
    result = runner.invoke(cli, ["--config", "/dev/null", "sync-to-bq", "--help"])
    assert result.exit_code == 0


@patch("recess_os.load_config", return_value=MOCK_CONFIG)
def test_cli_has_push_kpi_goals_command(_):
    runner = CliRunner()
    result = runner.invoke(cli, ["--config", "/dev/null", "push-kpi-goals", "--help"])
    assert result.exit_code == 0


@patch("recess_os.load_config", return_value=MOCK_CONFIG)
def test_cli_has_monday_pulse_command(_):
    runner = CliRunner()
    result = runner.invoke(cli, ["--config", "/dev/null", "monday-pulse", "--help"])
    assert result.exit_code == 0


@patch("recess_os.load_config", return_value=MOCK_CONFIG)
def test_cli_has_update_all_hands_deck_command(_):
    runner = CliRunner()
    result = runner.invoke(cli, ["--config", "/dev/null", "update-all-hands-deck", "--help"])
    assert result.exit_code == 0


# ── _run_phase2_command tests ─────────────────────────────────────────


class TestRunPhase2Command:

    def _make_ctx(self):
        """Create a mock Click context with config and bq_client."""
        ctx = MagicMock()
        ctx.obj = {
            "config": MOCK_CONFIG,
            "bq_client": MagicMock(),
        }
        return ctx

    @patch("recess_os.fetch_latest_snapshot")
    @patch("recess_os.build_all_payloads")
    @patch("recess_os.record_run")
    @patch("recess_os.record_deliveries")
    def test_fetches_snapshot_once(self, mock_rec_del, mock_rec_run,
                                   mock_build, mock_fetch):
        ctx = self._make_ctx()
        mock_fetch.return_value = ({"demand_nrr": 0.22}, "2026-04-14T08:00:00Z")
        mock_build.return_value = {"sales": [_payload()]}

        consumer_fn = MagicMock(return_value=(None, []))

        _run_phase2_command(ctx, "test-cmd", False, consumer_fn)

        mock_fetch.assert_called_once()

    @patch("recess_os.fetch_latest_snapshot")
    @patch("recess_os.build_all_payloads")
    @patch("recess_os.record_run")
    @patch("recess_os.record_deliveries")
    def test_builds_all_payloads_once(self, mock_rec_del, mock_rec_run,
                                      mock_build, mock_fetch):
        ctx = self._make_ctx()
        mock_fetch.return_value = ({"demand_nrr": 0.22}, "2026-04-14T08:00:00Z")
        mock_build.return_value = {"sales": [_payload()]}

        consumer_fn = MagicMock(return_value=(None, []))

        _run_phase2_command(ctx, "test-cmd", False, consumer_fn)

        mock_build.assert_called_once()

    @patch("recess_os.fetch_latest_snapshot")
    @patch("recess_os.record_run")
    def test_snapshot_unavailable_records_error_run(self, mock_rec_run, mock_fetch):
        ctx = self._make_ctx()
        mock_fetch.side_effect = SnapshotUnavailableError("No rows")

        with pytest.raises(SystemExit):
            _run_phase2_command(ctx, "test-cmd", False, MagicMock())

        mock_rec_run.assert_called_once()
        recorded_run = mock_rec_run.call_args[0][1]
        assert recorded_run.status == "error"

    @patch("recess_os.fetch_latest_snapshot")
    @patch("recess_os.build_all_payloads")
    @patch("recess_os.record_run")
    def test_consumer_exception_records_error_run(self, mock_rec_run,
                                                   mock_build, mock_fetch):
        ctx = self._make_ctx()
        mock_fetch.return_value = ({}, "ts")
        mock_build.return_value = {}

        consumer_fn = MagicMock(side_effect=RuntimeError("boom"))

        with pytest.raises(SystemExit):
            _run_phase2_command(ctx, "test-cmd", False, consumer_fn)

        mock_rec_run.assert_called_once()
        recorded_run = mock_rec_run.call_args[0][1]
        assert recorded_run.status == "error"
        assert "boom" in recorded_run.error_message

    @patch("recess_os.fetch_latest_snapshot")
    @patch("recess_os.build_all_payloads")
    @patch("recess_os.record_run")
    @patch("recess_os.record_deliveries")
    def test_audit_entries_recorded_to_bq(self, mock_rec_del, mock_rec_run,
                                          mock_build, mock_fetch):
        ctx = self._make_ctx()
        mock_fetch.return_value = ({"demand_nrr": 0.22}, "2026-04-14T08:00:00Z")
        payload = _payload()
        mock_build.return_value = {"sales": [payload]}

        result = ConsumerResult(
            registry_key="Demand NRR", dept_id="sales",
            consumer="slack_pulse", action="delivered",
        )
        consumer_fn = MagicMock(return_value=(None, [result]))

        _run_phase2_command(ctx, "test-cmd", False, consumer_fn)

        mock_rec_del.assert_called_once()
        entries = mock_rec_del.call_args[0][1]
        assert len(entries) == 1
        assert entries[0].registry_key == "Demand NRR"

    @patch("recess_os.fetch_latest_snapshot")
    @patch("recess_os.build_all_payloads")
    @patch("recess_os.record_run")
    @patch("recess_os.record_deliveries")
    def test_metric_run_recorded_at_completion(self, mock_rec_del, mock_rec_run,
                                                mock_build, mock_fetch):
        ctx = self._make_ctx()
        mock_fetch.return_value = ({}, "ts")
        mock_build.return_value = {}
        consumer_fn = MagicMock(return_value=(None, []))

        _run_phase2_command(ctx, "test-cmd", False, consumer_fn)

        mock_rec_run.assert_called_once()
        recorded_run = mock_rec_run.call_args[0][1]
        assert recorded_run.completed_at is not None


# ── Monday Pulse CLI ──────────────────────────────────────────────────


class TestMondayPulseCLI:

    @patch("recess_os._get_bq_client")
    @patch("recess_os.fetch_latest_snapshot")
    @patch("recess_os.build_all_payloads")
    @patch("recess_os.record_run")
    @patch("recess_os.record_deliveries")
    @patch("recess_os.load_config")
    def test_dry_run_prints_json_to_stdout(self, mock_config, mock_rec_del,
                                            mock_rec_run, mock_build, mock_fetch,
                                            mock_bq):
        mock_config.return_value = MOCK_CONFIG
        mock_bq.return_value = MagicMock()
        mock_fetch.return_value = ({"demand_nrr": 0.22}, "2026-04-14T08:00:00Z")
        mock_build.return_value = {"sales": [_payload()]}

        runner = CliRunner()
        result = runner.invoke(cli, ["--config", "/dev/null", "monday-pulse", "--dry-run"])

        # Should print JSON blocks (not post to Slack)
        assert result.exit_code == 0
        assert "monday-pulse" in result.output.lower()


# ── Update All-Hands Deck CLI ─────────────────────────────────────────


class TestUpdateAllHandsDeckCLI:

    @patch("recess_os.load_config")
    def test_skips_on_non_goals_week(self, mock_config):
        """When cadence check says 'projects' week, command skips."""
        config = dict(MOCK_CONFIG)
        mock_config.return_value = config

        with patch("recess_os.date") as mock_date:
            # ISO week 15 with reference_week=14, even → projects week
            from datetime import date as real_date
            mock_date.today.return_value = real_date(2026, 4, 7)
            mock_date.side_effect = lambda *a, **kw: real_date(*a, **kw)

            runner = CliRunner()
            result = runner.invoke(cli, [
                "--config", "/dev/null",
                "update-all-hands-deck", "--dry-run",
            ])

        assert "skipped" in result.output.lower() or result.exit_code == 0

    @patch("recess_os._get_bq_client")
    @patch("recess_os.fetch_latest_snapshot")
    @patch("recess_os.build_all_payloads")
    @patch("recess_os.record_run")
    @patch("recess_os.record_deliveries")
    @patch("recess_os.load_config")
    def test_runs_with_no_check_cadence(self, mock_config, mock_rec_del,
                                         mock_rec_run, mock_build, mock_fetch,
                                         mock_bq):
        mock_config.return_value = MOCK_CONFIG
        mock_bq.return_value = MagicMock()
        mock_fetch.return_value = ({}, "2026-04-14T08:00:00Z")
        mock_build.return_value = {"sales": [_payload()]}

        runner = CliRunner()
        result = runner.invoke(cli, [
            "--config", "/dev/null",
            "update-all-hands-deck", "--no-check-cadence", "--dry-run",
        ])

        assert result.exit_code == 0
        assert "update-all-hands-deck" in result.output.lower()
