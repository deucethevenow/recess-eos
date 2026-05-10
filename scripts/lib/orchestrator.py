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
from datetime import datetime, timezone
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

    Uses a broad 7-day partition filter to satisfy BQ's require_partition_filter
    on kpi_daily_snapshot (partitioned by snapshot_date). Within that window,
    takes the most recent row by snapshot_timestamp. If the snapshot is >25h old,
    downstream _is_stale() will flag it.

    Returns: (snapshot_row_dict, snapshot_timestamp_iso_string)
    Raises: SnapshotUnavailableError if zero rows returned.
    """
    rows = bq_client.query(
        "SELECT * FROM `stitchdata-384118.App_KPI_Dashboard.kpi_daily_snapshot` "
        "WHERE snapshot_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 7 DAY) "
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
    today: Optional[datetime] = None,
) -> dict[str, list[MetricPayload]]:
    """Build payloads for ALL departments in one pass.

    Iterates config["meetings"], calls build_metric_payloads() per meeting.
    Returns dict[dept_id → list[MetricPayload]].

    `today` is pinned ONCE here (naive UTC) and threaded into every per-dept
    build_metric_payloads call. That keeps day-math (days_elapsed, days_total)
    inside compute_pacing identical for every metric in a single pulse — no
    accidental drift if a dept's processing happens to straddle a UTC day
    boundary mid-run. When None, falls back to a deterministic naive-UTC
    timestamp here. Aware timestamps are stripped for compatibility with
    dashboard.utils.pacing's naive datetime arithmetic.

    This is the ONLY place build_metric_payloads() should be called during a run.
    Single invocation guarantees all consumers see identical data.
    """
    meetings = config.get("meetings", [])
    result: dict[str, list[MetricPayload]] = {}
    # Pin NAIVE — dashboard.utils.pacing._days_in_period constructs naive
    # q_start/q_end/year_start; subtracting an aware datetime there raises
    # TypeError that gets silently absorbed in _compute_path_b_fields and
    # null-s every Path B field. Caught by the C+E critic round 1.
    if today is not None and today.tzinfo is not None:
        today = today.replace(tzinfo=None)
    # When caller didn't pin, derive a deterministic naive-UTC `today`
    # (NOT `datetime.now()` — that returns naive in the container's TZ,
    # which Dockerfile.cron may set to America/New_York, leading to
    # day-boundary surprises around midnight UTC).
    pinned_today = today if today is not None else datetime.now(timezone.utc).replace(tzinfo=None)

    for meeting in meetings:
        dept_id = meeting.get("id", "unknown")
        payloads = build_metric_payloads(
            meeting_config=meeting,
            snapshot_row=snapshot_row,
            snapshot_timestamp=snapshot_ts,
            registry=registry,
            today=pinned_today,
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
