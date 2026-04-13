"""Orchestrator — shared infrastructure for all Recess OS metric consumers.

This module provides:
- fetch_latest_snapshot(): single BQ query for the latest snapshot row
- build_all_payloads(): builds MetricPayload for ALL departments in one pass
- ConsumerResult: standardized output from every consumer

Architecture:
    fetch_latest_snapshot()  →  build_all_payloads()  →  [consumer1, consumer2, ...]
    One snapshot.               One payload build.       Each gets the SAME payloads.
"""

from dataclasses import dataclass
from typing import Optional

from lib.metric_payloads import MetricPayload, build_metric_payloads


class SnapshotUnavailableError(Exception):
    """No snapshot row available. Run cannot proceed."""


@dataclass
class ConsumerResult:
    """Standardized result from any consumer (Asana Goals, Slack Pulse, Slides Deck).

    Every consumer returns list[ConsumerResult] — one per metric it processed.
    The orchestrator collects these for audit logging.
    """
    registry_key: str       # which metric
    dept_id: str            # which department
    consumer: str           # "asana_goal" | "slack_pulse" | "slides_deck"
    action: str             # "delivered" | "skipped" | "noop" | "error" | "dry_run"
    error_message: Optional[str] = None


def fetch_latest_snapshot(bq_client) -> tuple[dict, str]:
    """Fetch the single latest BQ snapshot row.

    Query is resilient — no CURRENT_DATE() filter. ORDER BY DESC LIMIT 1
    handles stale snapshots gracefully.

    Returns: (snapshot_row_dict, snapshot_timestamp_iso_string)
    Raises: SnapshotUnavailableError if zero rows returned.
    """
    rows = bq_client.query(
        "SELECT * FROM `stitchdata-384118.App_KPI_Dashboard.kpi_daily_snapshot` "
        "ORDER BY snapshot_timestamp DESC LIMIT 1"
    )

    if not rows:
        raise SnapshotUnavailableError(
            "No rows in kpi_daily_snapshot. Cannot build metric payloads."
        )

    row = rows[0]
    snapshot_ts = str(row.get("snapshot_timestamp", ""))

    return row, snapshot_ts


def build_all_payloads(
    config: dict,
    snapshot_row: dict,
    snapshot_ts: str,
    registry: dict = None,
) -> dict[str, list[MetricPayload]]:
    """Build payloads for ALL departments in one pass.

    Iterates config["meetings"], calls build_metric_payloads() per meeting.
    Returns dict[dept_id → list[MetricPayload]].

    This is the ONLY place build_metric_payloads() should be called during a run.
    Single invocation guarantees all consumers see identical data.
    """
    meetings = config.get("meetings", [])
    result: dict[str, list[MetricPayload]] = {}

    for meeting in meetings:
        dept_id = meeting.get("id", "unknown")
        payloads = build_metric_payloads(
            meeting_config=meeting,
            snapshot_row=snapshot_row,
            snapshot_timestamp=snapshot_ts,
            registry=registry,
        )
        result[dept_id] = payloads

    # Structural assertion: all payloads must share the same snapshot_timestamp
    all_timestamps = {
        p.snapshot_timestamp
        for dept_payloads in result.values()
        for p in dept_payloads
    }
    if len(all_timestamps) > 1:
        raise AssertionError(
            f"Payload timestamp drift detected: {all_timestamps}. "
            "All payloads must share a single snapshot_timestamp."
        )

    return result
