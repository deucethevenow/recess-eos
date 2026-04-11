"""Canonical metric payload layer — THE single source of truth for all metric values.

Every consumer (Asana Goals, Monday Pulse Slack, all-hands deck, leadership pre-read,
dept L10 scorecards) calls build_metric_payloads() and receives the SAME frozen
MetricPayload objects. No consumer queries BQ directly. No consumer computes transforms.
No consumer formats display values. This module does ALL of that, once, correctly.
"""
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Optional

from .metric_contract import resolve_metric_contract, MetricContract, ContractResolutionError
from .percentage_transforms import apply_transform
from .nan_safety import safe_float

STALE_THRESHOLD_HOURS = 25  # if snapshot_timestamp > 25h old, mark stale

SENSITIVITY_LEVELS = {"public": 0, "leadership": 1, "founders_only": 2}


@dataclass(frozen=True)
class MetricPayload:
    metric_name: str
    config_key: str
    registry_key: str
    snapshot_column: str
    raw_value: Optional[float]
    transformed_value: Optional[float]
    target: Optional[float]
    display_value: str
    metric_unit: str
    format_spec: str
    transform: str
    snapshot_timestamp: str
    sensitivity: str
    availability_state: str  # "live" | "needs_build" | "stale" | "error" | "null" | "manual"
    dept_id: str
    notes: Optional[str]


def build_metric_payloads(
    meeting_config: dict,
    snapshot_row: dict,
    snapshot_timestamp: str,
    registry: dict = None,
) -> list[MetricPayload]:
    """Build canonical metric payloads for a single meeting/dept from a BQ snapshot row.

    Args:
        meeting_config: The meeting entry from recess_os.yml (has scorecard_metrics).
        snapshot_row: A dict from the latest kpi_daily_snapshot row.
        snapshot_timestamp: ISO timestamp of when the snapshot was computed.
        registry: Optional METRIC_REGISTRY dict. Passed through to resolve_metric_contract.

    Returns:
        List of MetricPayload objects — one per scorecard metric. Frozen, immutable.
    """
    dept_id = meeting_config.get("id", "unknown")
    payloads = []

    for metric_config in meeting_config.get("scorecard_metrics", []):
        if not isinstance(metric_config, dict):
            continue

        try:
            contract = resolve_metric_contract(metric_config, registry=registry)
        except ContractResolutionError as e:
            payloads.append(_error_payload(metric_config, dept_id, str(e), snapshot_timestamp))
            continue

        # Determine availability
        if contract.status == "needs_build":
            payloads.append(_needs_build_payload(contract, dept_id, snapshot_timestamp))
            continue

        if contract.status == "manual":
            payloads.append(_manual_payload(contract, dept_id, snapshot_timestamp))
            continue

        if contract.status == "asana_goal":
            payloads.append(_asana_goal_payload(contract, dept_id, snapshot_timestamp))
            continue

        # Automated — pull from snapshot
        raw_value = safe_float(snapshot_row.get(contract.snapshot_column), default=None)

        # Check staleness
        availability = "live"
        if _is_stale(snapshot_timestamp):
            availability = "stale"
        if raw_value is None:
            availability = "null"

        # Apply transform
        transformed = None
        if raw_value is not None and contract.transform != "raw":
            transformed = apply_transform(
                raw_value=raw_value,
                transform=contract.transform,
                target=contract.target,
                baseline=metric_config.get("transform_baseline"),
            )
        elif raw_value is not None:
            transformed = raw_value

        # Format display value
        display = _format_display(raw_value, contract.format_spec, contract.null_behavior)

        payloads.append(MetricPayload(
            metric_name=contract.metric_name,
            config_key=metric_config.get("name", ""),
            registry_key=contract.registry_key or "",
            snapshot_column=contract.snapshot_column or "",
            raw_value=raw_value,
            transformed_value=transformed,
            target=contract.target,
            display_value=display,
            metric_unit=contract.format_spec,
            format_spec=contract.format_spec,
            transform=contract.transform,
            snapshot_timestamp=snapshot_timestamp,
            sensitivity=contract.sensitivity,
            availability_state=availability,
            dept_id=dept_id,
            notes=contract.notes,
        ))

    return payloads


def filter_by_sensitivity(payloads: list[MetricPayload], max_sensitivity: str) -> list[MetricPayload]:
    """Filter payloads to only include those at or below the given sensitivity level.

    Levels: public (0) < leadership (1) < founders_only (2)
    """
    max_level = SENSITIVITY_LEVELS.get(max_sensitivity, 0)
    return [p for p in payloads if SENSITIVITY_LEVELS.get(p.sensitivity, 0) <= max_level]


def _is_stale(timestamp_str: str) -> bool:
    """Returns True if the timestamp is older than STALE_THRESHOLD_HOURS."""
    try:
        ts = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
        age = datetime.now(timezone.utc) - ts
        return age > timedelta(hours=STALE_THRESHOLD_HOURS)
    except (ValueError, TypeError):
        return True  # unparseable = stale


def _format_display(value: Optional[float], format_spec: str, null_behavior: str) -> str:
    """Format a raw value for human display."""
    if value is None:
        return {
            "show_dash": "\u2014",
            "show_zero": "0",
            "hide": "",
            "show_needs_build": "\U0001f528 Needs Build",
        }.get(null_behavior, "\u2014")

    if format_spec == "currency":
        if abs(value) >= 1_000_000:
            return f"${value / 1_000_000:,.1f}M"
        elif abs(value) >= 1_000:
            return f"${value / 1_000:,.0f}K"
        return f"${value:,.0f}"
    elif format_spec == "percent":
        if abs(value) < 1:
            return f"{value * 100:.1f}%"
        return f"{value:.1f}%"
    elif format_spec in ("multiplier", "pipeline_gap"):
        return f"{value:.1f}x"
    elif format_spec == "days":
        return f"{value:.0f} days"
    elif format_spec in ("count", "number"):
        return f"{value:,.0f}"
    elif format_spec == "number_millions":
        return f"{value / 1_000_000:.1f}M"
    elif format_spec == "nps":
        return f"{value:.0f}"
    return f"{value}"


def _error_payload(config: dict, dept_id: str, error: str, ts: str) -> MetricPayload:
    return MetricPayload(
        metric_name=config.get("name", "Unknown"),
        config_key=config.get("name", ""), registry_key="", snapshot_column="",
        raw_value=None, transformed_value=None, target=None,
        display_value=f"\u26a0\ufe0f {error[:40]}", metric_unit="", format_spec="",
        transform="raw", snapshot_timestamp=ts, sensitivity="public",
        availability_state="error", dept_id=dept_id, notes=error,
    )


def _needs_build_payload(contract: MetricContract, dept_id: str, ts: str) -> MetricPayload:
    return MetricPayload(
        metric_name=contract.metric_name,
        config_key=contract.metric_name, registry_key=contract.registry_key or "",
        snapshot_column=contract.snapshot_column or "",
        raw_value=None, transformed_value=None, target=contract.target,
        display_value="\U0001f528 Needs Build", metric_unit=contract.format_spec,
        format_spec=contract.format_spec, transform=contract.transform,
        snapshot_timestamp=ts, sensitivity=contract.sensitivity,
        availability_state="needs_build", dept_id=dept_id, notes=contract.notes,
    )


def _manual_payload(contract: MetricContract, dept_id: str, ts: str) -> MetricPayload:
    return MetricPayload(
        metric_name=contract.metric_name,
        config_key=contract.metric_name, registry_key=contract.registry_key or "",
        snapshot_column="", raw_value=None, transformed_value=None,
        target=contract.target, display_value="\u26a0\ufe0f Manual", metric_unit=contract.format_spec,
        format_spec=contract.format_spec, transform="raw",
        snapshot_timestamp=ts, sensitivity=contract.sensitivity,
        availability_state="manual", dept_id=dept_id, notes=contract.notes,
    )


def _asana_goal_payload(contract: MetricContract, dept_id: str, ts: str) -> MetricPayload:
    # TODO: Query Asana Goal milestone completion % via API
    # For now, return a placeholder that downstream can fill
    return MetricPayload(
        metric_name=contract.metric_name,
        config_key=contract.metric_name, registry_key="",
        snapshot_column="", raw_value=None, transformed_value=None,
        target=contract.target, display_value="\U0001f3af Asana Goal",
        metric_unit=contract.format_spec, format_spec=contract.format_spec,
        transform="raw", snapshot_timestamp=ts, sensitivity=contract.sensitivity,
        availability_state="live", dept_id=dept_id,
        notes=f"Asana Goal {contract.asana_goal_id}",
    )
