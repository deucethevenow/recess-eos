"""Tests for run-level audit layer."""
from unittest.mock import MagicMock
import pytest

from lib.run_audit import (
    generate_run_id,
    MetricRun,
    DeliveryAuditEntry,
    record_run,
    record_deliveries,
    payload_to_audit_entry,
)
from lib.metric_payloads import MetricPayload


class TestGenerateRunId:
    def test_is_unique(self):
        ids = {generate_run_id() for _ in range(100)}
        assert len(ids) == 100

    def test_has_prefix(self):
        assert generate_run_id().startswith("run-")


class TestMetricRunLifecycle:
    def test_start_sets_timestamp(self):
        run = MetricRun("r1", "push-kpi-goals").start()
        assert run.started_at is not None
        assert run.started_at != ""

    def test_complete_success(self):
        entries = [
            DeliveryAuditEntry("r1", "push-kpi-goals", "PC", "sales",
                               "asana_goal", 2.1, 0.84, "2.1x", "live",
                               "2026-04-13T08:00:00Z", "delivered"),
        ]
        run = MetricRun("r1", "push-kpi-goals").start()
        run.complete(deliveries=entries)
        assert run.status == "success"
        assert run.metrics_count == 1
        assert run.completed_at is not None

    def test_complete_partial(self):
        """Mix of delivered + error = partial."""
        entries = [
            DeliveryAuditEntry("r1", "cmd", "A", "s", "asana_goal",
                               1, 1, "1", "live", "ts", "delivered"),
            DeliveryAuditEntry("r1", "cmd", "B", "s", "asana_goal",
                               None, None, "", "error", "ts", "error",
                               error_message="API fail"),
        ]
        run = MetricRun("r1", "push-kpi-goals").start()
        run.complete(deliveries=entries)
        assert run.status == "partial"

    def test_complete_all_errors(self):
        entries = [
            DeliveryAuditEntry("r1", "cmd", "A", "s", "asana_goal",
                               None, None, "", "error", "ts", "error"),
        ]
        run = MetricRun("r1", "push-kpi-goals").start()
        run.complete(deliveries=entries)
        assert run.status == "error"

    def test_complete_dry_run(self):
        entries = [
            DeliveryAuditEntry("r1", "cmd", "A", "s", "asana_goal",
                               2.1, 0.84, "2.1x", "live", "ts", "dry_run"),
        ]
        run = MetricRun("r1", "push-kpi-goals").start()
        run.complete(deliveries=entries)
        assert run.status == "dry_run"

    def test_complete_with_top_level_error(self):
        run = MetricRun("r1", "push-kpi-goals").start()
        run.complete(error="Config load failed")
        assert run.status == "error"
        assert run.error_message == "Config load failed"


class TestPayloadToAuditEntry:
    def test_converts_all_fields(self):
        payload = MetricPayload(
            metric_name="Pipeline Coverage", config_key="Pipeline Coverage",
            registry_key="Pipeline Coverage", snapshot_column="pipeline_coverage",
            raw_value=2.1, transformed_value=0.84, target=2.5,
            display_value="2.1x", metric_unit="multiplier", format_spec="multiplier",
            transform="percent_higher_is_better",
            snapshot_timestamp="2026-04-13T08:00:00Z",
            sensitivity="public", availability_state="live", dept_id="sales",
            notes=None,
        )
        entry = payload_to_audit_entry("run-123", "push-kpi-goals", payload,
                                       "asana_goal", "delivered")
        assert entry.run_id == "run-123"
        assert entry.command == "push-kpi-goals"
        assert entry.registry_key == "Pipeline Coverage"
        assert entry.consumer == "asana_goal"
        assert entry.raw_value == 2.1
        assert entry.transformed_value == 0.84
        assert entry.display_value == "2.1x"
        assert entry.action == "delivered"
        assert entry.delivered_at is not None

    def test_error_entry_includes_message(self):
        payload = MetricPayload(
            metric_name="Bad Metric", config_key="", registry_key="",
            snapshot_column="", raw_value=None, transformed_value=None,
            target=None, display_value="", metric_unit="", format_spec="",
            transform="raw", snapshot_timestamp="ts",
            sensitivity="public", availability_state="error", dept_id="sales",
            notes=None,
        )
        entry = payload_to_audit_entry("r1", "cmd", payload, "slack_pulse",
                                       "error", error="API timeout")
        assert entry.action == "error"
        assert entry.error_message == "API timeout"


class TestRecordToBQ:
    def test_record_run_calls_merge_events(self):
        mock_bq = MagicMock()
        run = MetricRun("r1", "push-kpi-goals", status="success",
                        metrics_count=5)
        record_run(mock_bq, run)
        mock_bq.merge_events.assert_called_once()
        args = mock_bq.merge_events.call_args
        assert args.args[0] == "eos_metric_runs"
        assert args.kwargs["natural_key_columns"] == ["run_id"]

    def test_record_deliveries_calls_merge_events(self):
        mock_bq = MagicMock()
        entry = DeliveryAuditEntry(
            run_id="r1", command="push-kpi-goals",
            registry_key="Pipeline Coverage", dept_id="sales",
            consumer="asana_goal", raw_value=2.1, transformed_value=0.84,
            display_value="2.1x", availability_state="live",
            snapshot_timestamp="2026-04-13T08:00:00Z", action="delivered",
        )
        record_deliveries(mock_bq, [entry], "r1")
        mock_bq.merge_events.assert_called_once()
        args = mock_bq.merge_events.call_args
        assert args.args[0] == "eos_metric_delivery_audit"
        assert args.kwargs["natural_key_columns"] == ["run_id", "registry_key", "consumer"]

    def test_record_deliveries_empty_is_noop(self):
        mock_bq = MagicMock()
        record_deliveries(mock_bq, [], "r1")
        mock_bq.merge_events.assert_not_called()
