"""Tests for KPI Goals pusher — idempotent push of MetricPayload values to Asana Goals.

Key behaviors tested:
1. Changed value → push to Asana, log as "success"
2. Unchanged value → skip push, log as "noop"
3. Dry-run → log as "dry_run", never touch Asana
4. Error handling → log as "error", continue with next goal
5. Non-automated metrics → log as "skipped"
"""
import pytest
from unittest.mock import MagicMock, patch
from dataclasses import dataclass
from typing import Optional

from lib.kpi_goals_pusher import (
    PushResult,
    push_kpi_goals,
    compute_goal_push_value,
)
from lib.metric_payloads import MetricPayload


def _make_payload(name="Test Metric", transformed_value=0.84, raw_value=2.1,
                  display_value="2.1x", sensitivity="public",
                  availability_state="live", dept_id="sales",
                  target=2.5, transform="percent_higher_is_better"):
    return MetricPayload(
        metric_name=name, config_key=name, registry_key=name,
        snapshot_column="test_col", raw_value=raw_value,
        transformed_value=transformed_value, target=target,
        display_value=display_value, metric_unit="multiplier",
        format_spec="multiplier", transform=transform,
        snapshot_timestamp="2026-04-13T08:00:00Z",
        sensitivity=sensitivity, availability_state=availability_state,
        dept_id=dept_id, notes=None,
    )


class TestComputeGoalPushValue:
    def test_uses_transformed_value_for_percentage_goals(self):
        """For percentage Asana Goals, push the transformed (0-1) value."""
        payload = _make_payload(transformed_value=0.84)
        result = compute_goal_push_value(payload, goal_metric_unit="percentage")
        assert result == 0.84

    def test_uses_raw_value_for_number_goals(self):
        """For number Asana Goals, push the raw BQ value."""
        payload = _make_payload(raw_value=42.0)
        result = compute_goal_push_value(payload, goal_metric_unit="number")
        assert result == 42.0

    def test_uses_raw_value_for_currency_goals(self):
        """For currency Asana Goals, push the raw BQ value."""
        payload = _make_payload(raw_value=1_250_000)
        result = compute_goal_push_value(payload, goal_metric_unit="currency")
        assert result == 1_250_000

    def test_null_transformed_returns_none(self):
        """If transformed_value is None, return None."""
        payload = _make_payload(transformed_value=None)
        result = compute_goal_push_value(payload, goal_metric_unit="percentage")
        assert result is None


class TestPushKpiGoals:
    def test_dry_run_never_calls_asana(self):
        """In dry-run mode, Asana is never called."""
        payload = _make_payload()
        goal_config = {"asana_goal_id": "123", "metric_unit": "percentage"}

        mock_asana = MagicMock()
        mock_bq = MagicMock()
        mock_bq.query.return_value = []  # no previous push

        results = push_kpi_goals(
            payloads=[payload],
            goal_configs=[goal_config],
            asana_client=mock_asana,
            bq_client=mock_bq,
            dry_run=True,
        )

        assert len(results) == 1
        assert results[0].action == "dry_run"
        mock_asana.goals_api.update_goal.assert_not_called()

    def test_noop_when_value_unchanged(self):
        """If last pushed value equals current, action is noop."""
        payload = _make_payload(transformed_value=0.84)
        goal_config = {"asana_goal_id": "123", "metric_unit": "percentage"}

        mock_asana = MagicMock()
        mock_bq = MagicMock()
        # Last push had same value
        mock_bq.query.return_value = [{"last_value": 0.84}]

        results = push_kpi_goals(
            payloads=[payload],
            goal_configs=[goal_config],
            asana_client=mock_asana,
            bq_client=mock_bq,
            dry_run=False,
        )

        assert len(results) == 1
        assert results[0].action == "noop"
        mock_asana.goals_api.update_goal.assert_not_called()

    def test_pushes_when_value_changed(self):
        """If value changed, push to Asana and log success."""
        payload = _make_payload(transformed_value=0.84)
        goal_config = {"asana_goal_id": "123", "metric_unit": "percentage"}

        mock_asana = MagicMock()
        mock_bq = MagicMock()
        # Last push had different value
        mock_bq.query.return_value = [{"last_value": 0.50}]

        results = push_kpi_goals(
            payloads=[payload],
            goal_configs=[goal_config],
            asana_client=mock_asana,
            bq_client=mock_bq,
            dry_run=False,
        )

        assert len(results) == 1
        assert results[0].action == "success"
        assert results[0].old_value == 0.50
        assert results[0].new_value == 0.84
        mock_asana.goals_api.update_goal.assert_called_once()

    def test_pushes_on_first_run(self):
        """If no previous push exists, push the value."""
        payload = _make_payload(transformed_value=0.84)
        goal_config = {"asana_goal_id": "123", "metric_unit": "percentage"}

        mock_asana = MagicMock()
        mock_bq = MagicMock()
        mock_bq.query.return_value = []  # no previous push

        results = push_kpi_goals(
            payloads=[payload],
            goal_configs=[goal_config],
            asana_client=mock_asana,
            bq_client=mock_bq,
            dry_run=False,
        )

        assert len(results) == 1
        assert results[0].action == "success"

    def test_skips_non_live_payloads(self):
        """needs_build payloads are skipped, not pushed."""
        payload = _make_payload(availability_state="needs_build", transformed_value=None)
        goal_config = {"asana_goal_id": "123", "metric_unit": "percentage"}

        results = push_kpi_goals(
            payloads=[payload],
            goal_configs=[goal_config],
            asana_client=MagicMock(),
            bq_client=MagicMock(),
            dry_run=False,
        )

        assert len(results) == 1
        assert results[0].action == "skipped"

    def test_handles_asana_error_gracefully(self):
        """If Asana push fails, log as error and continue."""
        payload = _make_payload(transformed_value=0.84)
        goal_config = {"asana_goal_id": "123", "metric_unit": "percentage"}

        mock_asana = MagicMock()
        mock_asana.goals_api.update_goal.side_effect = Exception("Asana API error")
        mock_bq = MagicMock()
        mock_bq.query.return_value = [{"last_value": 0.50}]

        results = push_kpi_goals(
            payloads=[payload],
            goal_configs=[goal_config],
            asana_client=mock_asana,
            bq_client=mock_bq,
            dry_run=False,
        )

        assert len(results) == 1
        assert results[0].action == "error"
        assert "Asana API error" in results[0].reason
