"""Rich-format metric renderer — single source of truth for the deck +
leadership-doc Sales scorecard rendering.

Imports the dashboard's existing pacing + target functions instead of
recomputing. Per Pattern 7 (registry GOD), the dashboard is the canonical
source for these calculations; this module is a thin adapter that maps
their outputs into the deck's 5-column shape:
    Metric / Target / Actual / Status / Trend

Why this exists:
  The leadership pre-read doc renders Sales metrics with rich
  Target / Actual / Status (with label) / Trend (pace + gap) columns. Until
  Session 5, the slash command's deck writer used a simpler combined
  display string from cron's `_render_live_metric`, which left Target +
  Status (text) + Trend mostly blank.

  Building a parallel renderer would create technical debt — the dashboard
  ALREADY computes pacing, deltas, status (via `compute_pacing`), and
  loads quarterly targets from Firestore (via `get_team_quota`). This
  module imports those existing functions and ONLY adds:
    1. The 4-state status comparator (Off-track Q vs Off-track A
       distinction — quarter-end is sooner so flagged separately).
    2. Per-metric configuration mapping `(metric_key, dept_id)` to the
       right `actual_q_key`, `actual_ytd_key`, `target_q_source`,
       `target_annual_source`.
    3. Format strings matching the leadership doc's exact shape:
       "Q2: $2,817,036 / Annual: $10,768,144"
       "Q: $227K (8%) / YTD: $2.59M (24%)"
       "🔴 Off-track Q"
       "Q Pace $836K / Gap -$609K"

Both the slash command's deck_writer AND the leadership-preread skill
will eventually call `render_rich_sales_metric`. That's how the two
surfaces converge to a single source of truth.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Dict, NamedTuple, Optional

from utils.formatters import safe_float  # type: ignore  # dashboard repo
from utils.pacing import compute_pacing  # type: ignore  # dashboard repo
from data.targets_manager import get_team_quota  # type: ignore  # dashboard repo


# --------------------------------------------------------------------------- #
# 4-state status thresholds                                                   #
# --------------------------------------------------------------------------- #
#
# Status states (priority order — first match wins):
#   🔴 Off-track Q  — quarter pace is critically behind; quarter ends sooner
#                     so this is the more-urgent state to flag.
#   🔴 Off-track A  — annual pace is critically behind; flagged when quarter
#                     pace is OK but YTD is behind annual target pace.
#   🟡 At-risk     — within tolerance band on either dimension.
#   🟢 On-track    — meeting or exceeding pace on BOTH dimensions.
#
# Thresholds (matching dashboard's pace_bar_card status colors):
#   actual/expected < 0.85  → off-track for that period
#   actual/expected ∈ [0.85, 1.0)  → at-risk
#   actual/expected ≥ 1.0   → on-track

OFF_TRACK_THRESHOLD = 0.85  # below this = critical
AT_RISK_THRESHOLD = 1.0  # below this but ≥ off-track = at-risk
ON_TRACK_THRESHOLD = 1.0  # ≥ this = on-track


def _ratio_from_pacing(pacing: Optional[Dict[str, Any]]) -> Optional[float]:
    """Convert compute_pacing()'s `pct` field (delta/expected, negative when
    behind) into the actual/expected ratio used by status thresholds.

    Returns None when pacing is None, expected is 0, or pct is None.
    """
    if pacing is None:
        return None
    pct = pacing.get("pct")
    if pct is None:
        return None
    return 1.0 + pct  # actual/expected = 1 + delta/expected


def compute_4_state_status(
    q_pacing: Optional[Dict[str, Any]],
    annual_pacing: Optional[Dict[str, Any]],
) -> tuple[str, str]:
    """4-state status with Off-track Q vs Off-track A distinction.

    Args:
        q_pacing: result dict from compute_pacing(period="quarter"), or None
                  when the metric has no quarterly target.
        annual_pacing: result dict from compute_pacing(period="year"), or
                  None when the metric has no annual target.

    Returns:
        (icon, label) tuple — e.g. ("🔴", "Off-track Q") or ("🟢", "On-track").

    Priority order: Off-track Q (most urgent) → Off-track A → At-risk →
    On-track. A metric can be off-track on BOTH dimensions; the priority
    surfaces the more time-critical issue (Q-end is sooner than year-end).
    """
    q_ratio = _ratio_from_pacing(q_pacing)
    a_ratio = _ratio_from_pacing(annual_pacing)

    if q_ratio is not None and q_ratio < OFF_TRACK_THRESHOLD:
        return "\U0001F534", "Off-track Q"
    if a_ratio is not None and a_ratio < OFF_TRACK_THRESHOLD:
        return "\U0001F534", "Off-track A"
    at_risk = (
        (q_ratio is not None and q_ratio < AT_RISK_THRESHOLD)
        or (a_ratio is not None and a_ratio < AT_RISK_THRESHOLD)
    )
    if at_risk:
        return "\U0001F7E1", "At-risk"
    return "\U0001F7E2", "On-track"


# --------------------------------------------------------------------------- #
# Format helpers                                                              #
# --------------------------------------------------------------------------- #


def _short_currency(value: float) -> str:
    """Format a dollar amount as a compact string: 1234567 → '$1.23M'.
    Returns '—' for None inputs (safe_float(None) returns 0, which would
    print as $0 — wrong for missing data)."""
    if value is None:
        return "—"
    v = safe_float(value)
    if v is None:
        return "—"
    av = abs(v)
    sign = "-" if v < 0 else ""
    if av >= 1_000_000:
        return f"{sign}${av / 1_000_000:.2f}M".replace(".00M", "M")
    if av >= 1_000:
        return f"{sign}${av / 1_000:.0f}K"
    return f"{sign}${av:.0f}"


def _full_currency(value: float) -> str:
    """Format a dollar amount with full precision: 2817036 → '$2,817,036'."""
    if value is None:
        return "—"
    v = safe_float(value)
    if v is None:
        return "—"
    return f"${v:,.0f}"


def _pct(numer: float, denom: float) -> str:
    """Compute and format numer/denom as a percent: '24%'. Returns '—' on
    division errors, zero denominator, or None inputs."""
    if numer is None or denom is None:
        return "—"
    n = safe_float(numer)
    d = safe_float(denom)
    if d is None or d == 0 or n is None:
        return "—"
    return f"{int(round((n / d) * 100))}%"


# --------------------------------------------------------------------------- #
# RichMetricPayload — the output shape the deck writer + leadership-doc       #
# writer both consume                                                         #
# --------------------------------------------------------------------------- #


class RichMetricPayload(NamedTuple):
    """Pre-formatted strings ready to drop into deck cells.

    Mirrors the leadership pre-read doc's Sales scorecard shape exactly so
    both surfaces render identically.
    """
    target_display: str  # "Q2: $2,817,036 / Annual: $10,768,144"
    actual_display: str  # "Q: $227K (8%) / YTD: $2.59M (24%)"
    status_icon: str  # "🔴 Off-track Q" — combined icon + label
    trend_display: str  # "Q Pace $836K / Gap -$609K"


# --------------------------------------------------------------------------- #
# Per-metric specs                                                            #
# --------------------------------------------------------------------------- #
#
# Each entry maps a registry metric name to the specific data sources +
# target keys + quarter label needed to render that metric. New Sales
# metrics get added here; this is the ONLY place metric routing is defined.

class _SalesMetricSpec(NamedTuple):
    """Data routing for one Sales rich-format metric."""
    actual_q_key: Optional[str]  # company_metrics key for Q actual ($)
    actual_ytd_key: Optional[str]  # company_metrics key for YTD actual ($)
    target_q_source: str  # "firestore_team_net_revenue_quota" |
                          # "firestore_team_bookings_quota" |
                          # "company_metrics:<key>" | "constant:<value>"
    target_annual_source: str  # same shape — annual target source


SALES_METRIC_SPECS: Dict[str, _SalesMetricSpec] = {
    # Reference implementation: Net Revenue YTD
    # Matches dashboard Company Overview "Year Actual Revenue" + leadership
    # doc "Net Revenue YTD" row.
    "Net Revenue YTD": _SalesMetricSpec(
        actual_q_key="demand_nrr_q_revenue",
        actual_ytd_key="revenue_actual",
        target_q_source="firestore_team_net_revenue_quota",
        target_annual_source="company_metrics:revenue_target",
    ),
    # Aliases — same metric under per-dept registry labels.
    "Demand Net Revenue YTD": _SalesMetricSpec(
        actual_q_key="demand_nrr_q_revenue",
        actual_ytd_key="revenue_actual",
        target_q_source="firestore_team_net_revenue_quota",
        target_annual_source="company_metrics:revenue_target",
    ),
}


def _resolve_quarter_label(today: date) -> str:
    """Return 'Q1' / 'Q2' / 'Q3' / 'Q4' for the quarter containing today."""
    q_num = (today.month - 1) // 3 + 1
    return f"Q{q_num}"


def _resolve_target(
    source: str,
    company_metrics: Dict[str, Any],
    quarter: str,
    today: date,
) -> Optional[float]:
    """Map a target_source string to a float value.

    Supported source forms:
      - "firestore_team_net_revenue_quota" — calls get_team_quota(year, quarter)
      - "firestore_team_bookings_quota"    — same, different field
      - "company_metrics:<key>"            — read company_metrics[key]
      - "constant:<float>"                 — literal value
    """
    if source.startswith("firestore_"):
        field = source[len("firestore_") :]
        try:
            quota = get_team_quota(year=today.year, quarter=quarter)
        except Exception:  # noqa: BLE001 — Firestore can be unavailable
            return None
        return safe_float(quota.get(field))
    if source.startswith("company_metrics:"):
        key = source[len("company_metrics:") :]
        return safe_float(company_metrics.get(key))
    if source.startswith("constant:"):
        return safe_float(source[len("constant:") :])
    return None


def render_rich_sales_metric(
    metric_key: str,
    dept_id: str,
    company_metrics: Dict[str, Any],
    today: Optional[date] = None,
) -> Optional[RichMetricPayload]:
    """Return a RichMetricPayload for the given metric, or None when the
    metric isn't configured for rich rendering (caller falls back to the
    simpler scorecard renderer).

    This is the ONE function that both the deck writer and (eventually)
    leadership-preread will call. Adding a new metric = adding an entry to
    SALES_METRIC_SPECS; no code branching elsewhere.
    """
    spec = SALES_METRIC_SPECS.get(metric_key)
    if spec is None:
        return None

    today = today or date.today()
    today_dt = datetime(today.year, today.month, today.day)
    quarter = _resolve_quarter_label(today)

    # Distinguish "key missing from company_metrics" (→ None, no rendering)
    # from "key present but value is 0" (legitimate zero — render as $0).
    # safe_float(None) returns 0 in the dashboard utils, which we MUST NOT
    # do here — it would erase the missing-data signal.
    raw_q = company_metrics.get(spec.actual_q_key) if spec.actual_q_key else None
    raw_ytd = company_metrics.get(spec.actual_ytd_key) if spec.actual_ytd_key else None
    actual_q = safe_float(raw_q) if raw_q is not None else None
    actual_ytd = safe_float(raw_ytd) if raw_ytd is not None else None
    target_q = _resolve_target(spec.target_q_source, company_metrics, quarter, today)
    target_annual = _resolve_target(spec.target_annual_source, company_metrics, quarter, today)

    q_pacing = (
        compute_pacing(actual=actual_q, target=target_q, period="quarter", today=today_dt)
        if actual_q is not None and target_q is not None
        else None
    )
    annual_pacing = (
        compute_pacing(actual=actual_ytd, target=target_annual, period="year", today=today_dt)
        if actual_ytd is not None and target_annual is not None
        else None
    )

    status_icon_only, status_label = compute_4_state_status(q_pacing, annual_pacing)

    # Format the four columns. Use compact currency for short fields,
    # full currency for Targets (which leadership reviews carefully).
    target_parts = []
    if target_q is not None:
        target_parts.append(f"{quarter}: {_full_currency(target_q)}")
    if target_annual is not None:
        target_parts.append(f"Annual: {_full_currency(target_annual)}")
    target_display = " / ".join(target_parts) if target_parts else "—"

    actual_parts = []
    if actual_q is not None and target_q is not None:
        actual_parts.append(
            f"Q: {_short_currency(actual_q)} ({_pct(actual_q, target_q)})"
        )
    elif actual_q is not None:
        actual_parts.append(f"Q: {_short_currency(actual_q)}")
    if actual_ytd is not None and target_annual is not None:
        actual_parts.append(
            f"YTD: {_short_currency(actual_ytd)} ({_pct(actual_ytd, target_annual)})"
        )
    elif actual_ytd is not None:
        actual_parts.append(f"YTD: {_short_currency(actual_ytd)}")
    actual_display = " / ".join(actual_parts) if actual_parts else "—"

    status_display = f"{status_icon_only} {status_label}"

    # Trend: "Q Pace $836K / Gap -$609K"
    if q_pacing is not None and q_pacing.get("expected") is not None:
        # "pace" in the leadership doc = projected end-of-quarter total at
        # current rate. compute_pacing's `expected` is what we'd have NOW
        # at on-pace; pace = actual / pacing_fraction (extrapolated).
        pf = q_pacing.get("pacing_fraction")
        pace_value = (actual_q / pf) if (pf and pf > 0 and actual_q is not None) else None
        gap_value = q_pacing.get("delta")  # actual - expected (negative if behind)
        if pace_value is not None and gap_value is not None:
            trend_display = (
                f"{quarter} Pace {_short_currency(pace_value)} / "
                f"Gap {_short_currency(gap_value)}"
            )
        else:
            trend_display = ""
    else:
        trend_display = ""

    return RichMetricPayload(
        target_display=target_display,
        actual_display=actual_display,
        status_icon=status_display,
        trend_display=trend_display,
    )
