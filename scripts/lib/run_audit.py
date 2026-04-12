"""Run-level audit for Phase 2 metric pipeline.

Every execution of push-kpi-goals / monday-pulse / all-hands-deck:
1. Builds payloads ONCE (single payload build per run)
2. Passes the same payloads to all consumers in the run
3. Records a DeliveryAuditEntry per metric per consumer (append-only)
4. Records a MetricRun at completion (one row per run_id — write-once)

Table semantics:
- eos_metric_runs: MUTABLE (one row per run, written at completion only).
  This is a completed-run audit table, NOT an in-progress run-state table.
  It cannot detect stuck or mid-run crashes.
- eos_metric_delivery_audit: APPEND-ONLY (immutable event log).

All writes go through RecessOSBQClient.merge_events().
"""
import uuid
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Optional


METRIC_RUN_SCHEMA = [
    {"name": "run_id", "field_type": "STRING", "mode": "REQUIRED"},
    {"name": "command", "field_type": "STRING"},
    {"name": "status", "field_type": "STRING"},
    {"name": "started_at", "field_type": "TIMESTAMP"},
    {"name": "completed_at", "field_type": "TIMESTAMP"},
    {"name": "snapshot_timestamp", "field_type": "TIMESTAMP"},
    {"name": "metrics_count", "field_type": "INT64"},
    {"name": "error_message", "field_type": "STRING"},
]

METRIC_DELIVERY_SCHEMA = [
    {"name": "run_id", "field_type": "STRING", "mode": "REQUIRED"},
    {"name": "command", "field_type": "STRING"},
    {"name": "registry_key", "field_type": "STRING"},
    {"name": "dept_id", "field_type": "STRING"},
    {"name": "consumer", "field_type": "STRING"},
    {"name": "raw_value", "field_type": "FLOAT64"},
    {"name": "transformed_value", "field_type": "FLOAT64"},
    {"name": "display_value", "field_type": "STRING"},
    {"name": "availability_state", "field_type": "STRING"},
    {"name": "snapshot_timestamp", "field_type": "TIMESTAMP"},
    {"name": "action", "field_type": "STRING"},
    {"name": "error_message", "field_type": "STRING"},
    {"name": "delivered_at", "field_type": "TIMESTAMP"},
]


def generate_run_id() -> str:
    """Generate a unique run ID for this execution."""
    return f"run-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8]}"


@dataclass
class MetricRun:
    """One row in eos_metric_runs. Written once at completion."""
    run_id: str
    command: str
    status: str = "success"
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    snapshot_timestamp: Optional[str] = None
    metrics_count: int = 0
    error_message: Optional[str] = None

    def start(self):
        self.started_at = datetime.now(timezone.utc).isoformat()
        return self

    def complete(self, deliveries: list = None, error: str = None):
        """Derive status from delivery actions.

        Partial: at least one error AND at least one delivered/noop.
        Error: all errors (or top-level error string provided).
        Dry_run: any dry_run action present.
        Success: everything else.
        """
        self.completed_at = datetime.now(timezone.utc).isoformat()

        if error:
            self.status = "error"
            self.error_message = error
            return self

        if not deliveries:
            self.status = "success"
            return self

        actions = {d.action for d in deliveries}
        has_errors = "error" in actions
        has_success = bool(actions & {"delivered", "noop"})
        has_dry_run = "dry_run" in actions

        if has_dry_run:
            self.status = "dry_run"
        elif has_errors and has_success:
            self.status = "partial"
        elif has_errors and not has_success:
            self.status = "error"
            self.error_message = f"{sum(1 for d in deliveries if d.action == 'error')} delivery errors"
        else:
            self.status = "success"

        self.metrics_count = len(deliveries)
        return self


@dataclass
class DeliveryAuditEntry:
    """One row in eos_metric_delivery_audit. Append-only — never modified."""
    run_id: str
    command: str
    registry_key: str
    dept_id: str
    consumer: str
    raw_value: Optional[float]
    transformed_value: Optional[float]
    display_value: str
    availability_state: str
    snapshot_timestamp: str
    action: str
    error_message: Optional[str] = None
    delivered_at: Optional[str] = None

    def __post_init__(self):
        if self.delivered_at is None:
            self.delivered_at = datetime.now(timezone.utc).isoformat()


def record_run(bq_client, run: MetricRun) -> None:
    """Write a completed MetricRun row to eos_metric_runs."""
    bq_client.merge_events(
        "eos_metric_runs",
        [asdict(run)],
        natural_key_columns=["run_id"],
        run_id=run.run_id,
    )


def record_deliveries(bq_client, entries: list[DeliveryAuditEntry], run_id: str) -> None:
    """Append delivery audit entries to eos_metric_delivery_audit."""
    if not entries:
        return
    bq_client.merge_events(
        "eos_metric_delivery_audit",
        [asdict(e) for e in entries],
        natural_key_columns=["run_id", "registry_key", "consumer"],
        run_id=run_id,
    )


def payload_to_audit_entry(
    run_id: str,
    command: str,
    payload,
    consumer: str,
    action: str,
    error: str = None,
) -> DeliveryAuditEntry:
    """Convert a MetricPayload + consumer action into an audit entry."""
    return DeliveryAuditEntry(
        run_id=run_id,
        command=command,
        registry_key=payload.registry_key,
        dept_id=payload.dept_id,
        consumer=consumer,
        raw_value=payload.raw_value,
        transformed_value=payload.transformed_value,
        display_value=payload.display_value,
        availability_state=payload.availability_state,
        snapshot_timestamp=payload.snapshot_timestamp,
        action=action,
        error_message=error,
    )
