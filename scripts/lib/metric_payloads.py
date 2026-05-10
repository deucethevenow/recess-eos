"""Canonical metric payload layer — THE single source of truth for all metric values.

Every consumer (Asana Goals, Monday Pulse Slack, all-hands deck, leadership pre-read,
dept L10 scorecards) calls build_metric_payloads() and receives the SAME frozen
MetricPayload objects. No consumer queries BQ directly. No consumer computes transforms.
No consumer formats display values. This module does ALL of that, once, correctly.
"""
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Literal, Optional, TypedDict, get_args

from .metric_contract import resolve_metric_contract, MetricContract, ContractResolutionError
from .percentage_transforms import apply_transform
from .nan_safety import _is_bad_number

STALE_THRESHOLD_HOURS = 25  # if snapshot_timestamp > 25h old, mark stale

Status3State = Literal["on_track", "at_risk", "off_track"]
# Mirrors dashboard.utils.pacing.Period verbatim — kept local because that
# module is imported lazily inside _compute_path_b_fields (Cloud Run cron
# may run without the dashboard mount). Annotations need Period at import
# time, so we can't import it lazily. If the dashboard adds a period value,
# update this in lockstep.
Period = Literal["month", "quarter", "year"]
_VALID_PERIODS = frozenset(get_args(Period))


class PathBFields(TypedDict):
    pace_value: Optional[float]
    gap_value: Optional[float]
    status_3state: Optional[Status3State]


def _safe_optional_float(value) -> Optional[float]:
    """Return float(value) or None for null/nan/inf/non-numeric.

    This is the null-aware sibling of nan_safety.safe_float(): we need to
    preserve None as a distinct signal (metric missing from snapshot) rather
    than coerce to 0.0. safe_float's contract is 'always return a float',
    which would destroy the null signal.
    """
    if _is_bad_number(value):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None

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
    # Path B fields (Phase B+) — pace/gap/3-state status. Defaults `= None` so
    # the four stub-payload helpers (_error/_needs_build/_manual/_asana_goal)
    # constructing positionally don't break, and so missing-data metrics pass
    # through cleanly without fabricating signals.
    pace_value: Optional[float] = None       # signed delta from expected (positive=ahead)
    gap_value: Optional[float] = None        # max(0, target - raw_value), always >= 0
    status_3state: Optional[Status3State] = None
    target_display: Optional[str] = None     # formatted target ("$1.5M", "92%", etc.) or None when target is None


def build_metric_payloads(
    meeting_config: dict,
    snapshot_row: dict,
    snapshot_timestamp: str,
    registry: dict = None,
    today: Optional[datetime] = None,
) -> list[MetricPayload]:
    """Build canonical metric payloads for a single meeting/dept from a BQ snapshot row.

    Args:
        meeting_config: The meeting entry from recess_os.yml (has scorecard_metrics).
        snapshot_row: A dict from the latest kpi_daily_snapshot row.
        snapshot_timestamp: ISO timestamp of when the snapshot was computed.
        registry: Optional METRIC_REGISTRY dict. Passed through to resolve_metric_contract.
        today: Optional pinned NAIVE timestamp threaded into pace math.
            When None, this function pins a deterministic naive-UTC
            timestamp once and threads it through to _compute_path_b_fields
            -> compute_pacing. Within a single call, day-math
            (days_elapsed, days_total) inside compute_pacing is therefore
            computed once instead of per-metric (~63x reduction within one
            dept's payloads). Aware timestamps (tzinfo not None) are
            stripped for compatibility with dashboard.utils.pacing's naive
            datetime arithmetic.
            Production path: orchestrator.build_all_payloads pins `today`
            ONCE for the whole pulse and threads it through every dept
            call, so all depts share the same `today` (no UTC-day-boundary
            drift mid-run). Direct callers (tests, the four surface
            adapters) get an independent per-call `today` when they don't
            pass it.

    Returns:
        List of MetricPayload objects — one per scorecard metric. Frozen, immutable.
    """
    dept_id = meeting_config.get("id", "unknown")
    payloads = []
    # Pin a NAIVE datetime to match dashboard.utils.pacing._days_in_period,
    # which constructs naive q_start/q_end/year_start. Subtracting an
    # aware datetime against a naive one raises TypeError, which the
    # _compute_path_b_fields exception handler silently absorbs into
    # all-None Path B fields — a footgun caught by the C+E critic round 1.
    if today is not None and today.tzinfo is not None:
        today = today.replace(tzinfo=None)
    # When caller didn't pin, derive a deterministic naive-UTC `today`
    # (NOT `datetime.now()` — that returns naive in the container's TZ,
    # which Dockerfile.cron may set to America/New_York, leading to
    # day-boundary surprises around midnight UTC).
    pinned_today = today if today is not None else datetime.now(timezone.utc).replace(tzinfo=None)

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
        raw_value = _safe_optional_float(snapshot_row.get(contract.snapshot_column))

        # Check staleness first, then null. Precedence order (deliberate):
        # null ALWAYS wins over stale, because a null value is a "no data"
        # signal regardless of freshness, and consumers render it as a dash.
        # Stale + null ambiguity is resolved by the `notes` field downstream.
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
                baseline=None,  # reserved for percent_lower_is_better (from registry when needed)
            )
        elif raw_value is not None:
            transformed = raw_value

        # Format display value
        display = _format_display(raw_value, contract.format_spec, contract.null_behavior)

        # Path B (Phase B+): pace/gap/status_3state. Pace math lives ONCE here so
        # all four surface adapters (Slack/Deck/Doc/Founders) get identical values
        # by construction — adapters never recompute. Period from registry; falls
        # back to snapshot_column suffix inference for entries missing a `period:`
        # field (most metrics today, until the dashboard registry update lands).
        period = contract.period or _infer_period(contract.snapshot_column)
        path_b = _compute_path_b_fields(
            raw_value=raw_value,
            target=contract.target,
            period=period,
            today=pinned_today,
        )

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
            pace_value=path_b["pace_value"],
            gap_value=path_b["gap_value"],
            status_3state=path_b["status_3state"],
            target_display=_compute_target_display(contract.target, contract.format_spec),
        ))

    return payloads


def _infer_period(snapshot_column: Optional[str]) -> Optional[Period]:
    """Best-effort period inference from a snapshot column name.

    Used as fallback when the registry entry doesn't declare a `period` field.
    Returns None for ambiguous columns (snapshot counts, ratios, weekly counters).
    Conservative: when in doubt, return None — _compute_path_b_fields will then
    short-circuit to None-fields rather than fabricate pace against the wrong
    fraction-of-period.
    """
    if not snapshot_column:
        return None
    name = snapshot_column.lower()
    if name.endswith("_ytd") or name.endswith("ytd"):
        return "year"
    if name.endswith("_qtd") or name.endswith("_q") or name.endswith("qtd"):
        return "quarter"
    if name.endswith("_mtd"):
        return "month"
    return None


def _compute_path_b_fields(
    raw_value: Optional[float],
    target: Optional[float],
    period: Optional[Period] = None,
    today: Optional[datetime] = None,
) -> PathBFields:
    """Path B: pace + gap + 3-state status via dashboard.utils.pacing.compute_pacing.

    `period` defaults to None (was "quarter" before Phase C+E). The production
    caller in this module passes `period` explicitly, so the default change
    is benign today — but a future direct caller that omits `period` now
    safely degrades to None-fields rather than silently mis-pacing an annual
    or monthly metric against a quarter fraction.

    Returns {pace_value, gap_value, status_3state}. Every field is None if any
    guard fails — never fabricates signals from missing/bad data.

    Semantics:
      pace_value    = signed delta from expected (positive=ahead, negative=behind)
      gap_value     = max(0, target - raw_value), always >= 0 (remaining-to-target)
      status_3state = "on_track" if pct >= 0
                      "at_risk"  if -0.30 <= pct < 0
                      "off_track" if pct < -0.30
                      None when no comparison is meaningful

    Guards (ordered, fail-loud None on each):
      1. None inputs (missing data)
      2. NaN/inf inputs — `compute_pacing` calls `safe_float()` internally which
         silently coerces NaN->0; would render "100% behind pace" for missing
         data without this guard.
      3. target=0 (no quota → no meaningful comparison; avoid divide-by-zero)
      4. period=None (forecast metrics, snapshot counts → no time fraction)
      5. ImportError on dashboard.utils.pacing — Cloud Run image without
         dashboard mount returns None-fields rather than crashing.
    """
    if raw_value is None or target is None:
        return {"pace_value": None, "gap_value": None, "status_3state": None}
    if _is_bad_number(raw_value) or _is_bad_number(target):
        return {"pace_value": None, "gap_value": None, "status_3state": None}
    if target == 0:
        return {"pace_value": None, "gap_value": None, "status_3state": None}
    if period is None or period not in _VALID_PERIODS:
        return {"pace_value": None, "gap_value": None, "status_3state": None}

    try:
        from dashboard.utils.pacing import compute_pacing
    except ImportError:
        return {"pace_value": None, "gap_value": None, "status_3state": None}

    # Defense-in-depth: dashboard.utils.pacing._days_in_period subtracts
    # `today` against naive q_start / year_start datetimes. An aware `today`
    # raises TypeError that the except-clause below absorbs into all-None
    # Path B fields. Strip tzinfo here so direct callers (tests, ad-hoc
    # invocations) can pass aware safely. The two pinning sites
    # (build_metric_payloads, build_all_payloads) already strip; this is
    # a redundant safety net for direct callers. See C+E critic round 1.
    if today is not None and today.tzinfo is not None:
        today = today.replace(tzinfo=None)

    try:
        pacing = compute_pacing(raw_value, target, period, today=today)
    except (ValueError, TypeError):
        return {"pace_value": None, "gap_value": None, "status_3state": None}

    delta = pacing.get("delta")
    pct = pacing.get("pct")

    if _is_bad_number(delta):
        return {"pace_value": None, "gap_value": None, "status_3state": None}

    if pct is None or _is_bad_number(pct):
        status = None
    elif pct >= 0:
        status = "on_track"
    elif pct >= -0.30:
        status = "at_risk"
    else:
        status = "off_track"

    return {
        "pace_value": float(delta),
        "gap_value": max(0.0, float(target) - float(raw_value)),
        "status_3state": status,
    }


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


def _compute_target_display(target: Optional[float], format_spec: str) -> Optional[str]:
    """Format a target for human display, or return None when target is missing.

    Lifted out of consumers so MetricPayload carries the formatted string
    directly — no consumer needs to import private formatters or reformat.
    """
    if target is None:
        return None
    return _format_display(target, format_spec, "show_dash")


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
        if abs(value) <= 1:
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
        target_display=_compute_target_display(contract.target, contract.format_spec),
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
        target_display=_compute_target_display(contract.target, contract.format_spec),
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
        target_display=_compute_target_display(contract.target, contract.format_spec),
    )
