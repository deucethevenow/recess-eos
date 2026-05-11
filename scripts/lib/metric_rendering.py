"""Phase H.2 — H-adapter producer module.

Renders MetricPayloads to the legacy RenderedRow shape consumed by Slack/deck/
doc writers. Delegates MOST formatting to dashboard's _render_metric_line, with
ONE narrow local override: the W.1 trap (live raw_value + scorecard_status=
needs_build in the registry). Without that override dashboard short-circuits
to "🔨 Needs Build" — exactly the F-1 bug Phase H exists to fix.

Why H-adapter (not H-port): _render_live_metric is only 47 LOC but its
transitive call paths pull 7 dashboard-side live-data fetchers spanning
BigQuery, Firestore, and the Asana Goals API. Porting them into eos would
distribute the cross-repo boundary across 7 import sites; the H-adapter
consolidates it into ONE call site (_render_metric_line) and pins the
signature via module-level inspect.signature assertions. See Phase H plan
Appendix B + the H.1 audit at:
    context/plans/2026-05-10-phase-h-pathb-consumer-migration.md

H.2 ships this module ONLY — no consumer is wired to it yet. H.3 routes
Slack/deck/doc writers through build_rich_displays; H.4a flips
monday_kpi_update.main() to drive only the new pipeline.
"""
import inspect
from datetime import date
from typing import Any, Callable, Dict, List

from .metric_payloads import MetricPayload
from .rendered_row import RenderedRow
from . import dashboard_paths  # noqa: F401  ## side-effect: sys.path setup

from post_monday_pulse import (  # type: ignore  # noqa: E402
    _render_live_metric,
    _render_metric_line,
)
from data.metric_registry import (  # type: ignore  # noqa: E402
    METRIC_REGISTRY,
    get_scorecard_dept_sensitivity,
    get_scorecard_label,
)


_EXPECTED_RENDER_METRIC_LINE_SIG = "(canonical_name, entry, dept, company_metrics)"
_EXPECTED_RENDER_LIVE_METRIC_SIG = "(entry, dept, company_metrics, canonical_name)"


def _assert_dashboard_signature(func: Callable, expected: str) -> None:
    """Fail LOUD at import time if a pinned dashboard private API drifts.

    Compares parameter NAMES (in order), ignoring annotations and defaults —
    those are cosmetic and may shift between Python versions or dashboard
    refactors. What matters for cross-repo call safety is name + order:
    rename `dept` → `dept_id`, reorder args, add/remove params → all break us
    and all caught here.

    Known false-positive surface: adding a new OPTIONAL kwarg at the END would
    fire this assertion even though existing positional callers keep working.
    That's intentional over-conservatism — better to manually re-audit when
    dashboard adds new kwargs than to miss a real drift that silently changes
    return shape. To bless a new kwarg, update _EXPECTED_RENDER_*_SIG.
    """
    params = inspect.signature(func).parameters
    actual = "(" + ", ".join(p.name for p in params.values()) + ")"
    if actual != expected:
        raise RuntimeError(
            f"Cross-repo signature drift: dashboard's "
            f"post_monday_pulse.{func.__name__} parameter list changed from "
            f"{expected} to {actual}. Phase H.2 needs to be re-audited. See "
            f"context/plans/2026-05-10-phase-h-pathb-consumer-migration.md."
        )


_assert_dashboard_signature(_render_metric_line, _EXPECTED_RENDER_METRIC_LINE_SIG)
_assert_dashboard_signature(_render_live_metric, _EXPECTED_RENDER_LIVE_METRIC_SIG)


def _invoke_dashboard_renderer(
    payload: MetricPayload,
    entry: Dict[str, Any],
    dept_id: str,
    company_metrics: Dict[str, Any],
) -> str:
    """The single cross-repo call site for dashboard's _render_metric_line.

    Takes `entry` as a parameter (not looked up here) so the caller can do
    ONE registry lookup per payload and reuse `entry` for label + sensitivity.
    Centralized for grep-ability (find all dashboard-rendering call sites) and
    so future changes (logging, retry, caching) live in one place.

    _render_metric_line internally dispatches the full cascade (asana_goal
    short-circuit, special-metric override, sales-per-page, _render_live_metric,
    target suffix append) and returns the fully-formatted bullet line:
        "• *<label>*: <body>  ·  target <target>"
    """
    return _render_metric_line(payload.registry_key, entry, dept_id, company_metrics)


def _render_via_payload(
    payload: MetricPayload,
    entry: Dict[str, Any],
    dept_id: str,
) -> str:
    """Render a bullet line locally, bypassing dashboard's needs_build short-circuit.

    Used when payload.availability_state == "live" AND
    entry.scorecard_status == "needs_build" — the F-1 case. Dashboard's
    _render_metric_line (post_monday_pulse.py:935-936) short-circuits to
    "🔨 Needs Build" for needs_build entries, ignoring eos's live raw_value.
    This local renderer mirrors dashboard's bullet shape exactly so
    cross-surface parity holds:
        "• *<label>*: <body>  ·  target <target>"

    When dashboard flips W.1 entries from needs_build → live, this branch stops
    firing automatically — the bypass condition is data-driven, not list-driven.
    """
    label = get_scorecard_label(entry, dept_id, payload.registry_key)
    body = payload.display_value or "—"
    suffix = (
        f"  ·  target {payload.target_display}" if payload.target_display else ""
    )
    return f"• *{label}*: {body}{suffix}"


def _is_w1_bypass_case(payload: MetricPayload, entry: Dict[str, Any]) -> bool:
    """True when eos has a live value but registry still marks the metric as
    needs_build (the W.1 F-1 trap). Encapsulated as a function so the test
    suite can pin the condition directly and so the dispatcher reads cleanly.
    """
    return (
        payload.availability_state == "live"
        and entry.get("scorecard_status") == "needs_build"
    )


def build_rich_displays(
    payloads_per_dept: Dict[str, List[MetricPayload]],
    company_metrics: Dict[str, Any],
    today: date,  # noqa: ARG001 — signature parity with render_one_row; see docstring
) -> Dict[str, Dict[str, Any]]:
    """Build the legacy rendered_per_dept shape from MetricPayloads.

    Output:
        {dept_id: {"scorecard_rows": [RenderedRow, ...]}}

    Dispatch per payload:
      - W.1 bypass case (live raw_value + needs_build status): render locally
        via _render_via_payload (the F-1 fix).
      - Everything else: route through dashboard's _render_metric_line via
        _invoke_dashboard_renderer.

    `today` is currently unused — the H-adapter delegates all temporal math
    to dashboard, which derives its own time horizon from company_metrics +
    entry config. The parameter is held in the signature for symmetry with
    render_one_row(entry, dept_id, company_metrics, today); H.3 callers that
    were pinning `today` for render_one_row can pass the same value here
    without code changes. If a future override needs time, this is where it
    threads.

    Consumer writers (slack/deck/doc) keep reading RenderedRow.display
    unchanged after H.3.
    """
    output: Dict[str, Dict[str, Any]] = {}
    for dept_id, payloads in payloads_per_dept.items():
        rows: List[RenderedRow] = []
        for payload in payloads:
            entry = METRIC_REGISTRY[payload.registry_key]
            if _is_w1_bypass_case(payload, entry):
                display = _render_via_payload(payload, entry, dept_id)
            else:
                display = _invoke_dashboard_renderer(
                    payload, entry, dept_id, company_metrics
                )
            display_label = get_scorecard_label(entry, dept_id, payload.registry_key)
            sensitivity = get_scorecard_dept_sensitivity(entry, dept_id) or "public"
            rows.append(
                RenderedRow(
                    metric_name=payload.registry_key,
                    display_label=display_label,
                    dept_id=dept_id,
                    sensitivity=sensitivity,
                    actual_raw=payload.raw_value,
                    target_raw=payload.target,
                    status_icon="⚪",
                    display=display,
                    actual_display=display,
                    target_display=None,
                    trend_display=None,
                    is_phase2_placeholder=False,
                    is_special_override=False,
                )
            )
        output[dept_id] = {"scorecard_rows": rows}
    return output
