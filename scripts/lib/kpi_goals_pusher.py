"""KPI Goals pusher — idempotent push of MetricPayload values to Asana Goals.

Consumes MetricPayload objects (the canonical single source of truth).
NEVER queries BQ for metric values — only reads the history table for idempotency.

Flow:
1. Receive MetricPayload + goal config (asana_goal_id, metric_unit)
2. Compute push value from payload (transformed_value for %, raw_value for count/currency)
3. Check eos_goal_metric_history for last pushed value
4. If unchanged → noop (don't push, log noop)
5. If changed → push to Asana, log success
6. If dry-run → log dry_run, never touch Asana
"""
from dataclasses import dataclass
from typing import Optional
import logging

from .nan_safety import safe_float

logger = logging.getLogger(__name__)


@dataclass
class PushResult:
    goal_id: str
    goal_name: str
    action: str  # "success" | "noop" | "dry_run" | "error" | "skipped"
    old_value: Optional[float]
    new_value: Optional[float]
    reason: Optional[str] = None


def compute_goal_push_value(payload, goal_metric_unit: str) -> Optional[float]:
    """Compute the value to push to an Asana Goal from a MetricPayload.

    For percentage Goals: use transformed_value (0.0-1.0 scale)
    For number/currency Goals: use raw_value (literal BQ value)
    """
    if goal_metric_unit == "percentage":
        return payload.transformed_value
    return payload.raw_value


def push_kpi_goals(
    payloads: list,
    goal_configs: list[dict],
    asana_client,
    bq_client,
    dry_run: bool = False,
    run_id: str = None,
) -> list[PushResult]:
    """Push metric values to Asana Goals with idempotency.

    Args:
        payloads: List of MetricPayload objects (one per goal to push)
        goal_configs: List of dicts with asana_goal_id and metric_unit per payload
        asana_client: RecessAsanaClient instance
        bq_client: RecessOSBQClient instance
        dry_run: If True, log as dry_run and never touch Asana
        run_id: Optional sync run ID for BQ history logging
    """
    results = []

    for payload, goal_config in zip(payloads, goal_configs):
        goal_id = goal_config.get("asana_goal_id", "unknown")
        metric_unit = goal_config.get("metric_unit", "percentage")

        # Skip non-live payloads
        if payload.availability_state not in ("live", "stale"):
            results.append(PushResult(
                goal_id=goal_id,
                goal_name=payload.metric_name,
                action="skipped",
                old_value=None,
                new_value=None,
                reason="availability_state=" + payload.availability_state,
            ))
            continue

        # Compute push value
        push_value = compute_goal_push_value(payload, metric_unit)
        if push_value is None:
            results.append(PushResult(
                goal_id=goal_id,
                goal_name=payload.metric_name,
                action="skipped",
                old_value=None,
                new_value=None,
                reason="push_value is None",
            ))
            continue

        # Check last pushed value for idempotency
        last_value = _get_last_pushed_value(bq_client, goal_id)

        # Dry run — log and skip
        if dry_run:
            results.append(PushResult(
                goal_id=goal_id,
                goal_name=payload.metric_name,
                action="dry_run",
                old_value=last_value,
                new_value=push_value,
                reason="dry_run=True",
            ))
            continue

        # Idempotency check
        if last_value is not None and abs(safe_float(last_value) - safe_float(push_value)) < 1e-9:
            results.append(PushResult(
                goal_id=goal_id,
                goal_name=payload.metric_name,
                action="noop",
                old_value=last_value,
                new_value=push_value,
                reason="value unchanged",
            ))
            continue

        # Push to Asana
        try:
            asana_client.goals_api.update_goal(
                goal_id,
                {"data": {"metric": {"current_number_value": push_value}}},
                {}
            )
            results.append(PushResult(
                goal_id=goal_id,
                goal_name=payload.metric_name,
                action="success",
                old_value=last_value,
                new_value=push_value,
            ))
            logger.info(
                "Pushed %s → goal %s: %s → %s",
                payload.metric_name, goal_id, last_value, push_value,
            )
        except Exception as e:
            logger.error(
                "Failed to push %s → goal %s: %s",
                payload.metric_name, goal_id, e,
            )
            results.append(PushResult(
                goal_id=goal_id,
                goal_name=payload.metric_name,
                action="error",
                old_value=last_value,
                new_value=push_value,
                reason=str(e),
            ))

    return results


def _get_last_pushed_value(bq_client, goal_id: str) -> Optional[float]:
    """Query eos_goal_metric_history for the last pushed value for this goal."""
    try:
        rows = bq_client.query(
            "SELECT pushed_value as last_value "
            "FROM `" + bq_client.full_table_id('eos_goal_metric_history') + "` "
            "WHERE asana_goal_id = '" + goal_id + "' AND action = 'success' "
            "ORDER BY pushed_at DESC LIMIT 1"
        )
        if rows:
            raw = rows[0].get("last_value")
            return safe_float(raw) if raw is not None else None
    except Exception:
        pass  # first run or table doesn't exist yet
    return None
