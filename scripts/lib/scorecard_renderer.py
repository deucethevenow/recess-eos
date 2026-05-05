"""render_one_row — the single rendering function all surface writers consume.

Per v3.8 Patch 1 / Patch 8 cascade order:
  Step 0a: ENGINEERING_LIVE_METRICS — live-function dispatch (MUST precede Step 0b).
  Step 0b: needs_build → "🔨 (Phase 2 migration)" placeholder.
  Step 0c: asana_goal status → cron's _render_asana_goal (Asana Goals API path).
  Step 1-4: existing v3.5 cascade — handled by cron's _render_live_metric
            (special overrides, sales-per-page, scope=both, single value).

Cron parity divergences (deliberate):
  - Cron's needs_build placeholder = "🔨 Needs Build" (post_monday_pulse.py:933).
    Slash command uses "🔨 (Phase 2 migration)" per v3.8 plan. Documented for
    cut-over: cron and slash command will produce different placeholder text
    until cron is retired (Session 3 / Patch 11).

Target resolution (Patch 7 wiring):
  Targets resolve via cron's _fmt_target FIRST (registry per-dept override). When
  that returns None, fall back to STATIC_SCORECARD_TARGETS (the slash-command-
  owned 18-key map for metrics whose targets are hardcoded in dashboard render
  code instead of the registry).
"""
import os
import re
import sys
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Tuple

DASHBOARD_REPO = Path(
    os.environ.get(
        "KPI_DASHBOARD_REPO",
        "/Users/deucethevenowworkm1/Projects/company-kpi-dashboard",
    )
)
for _p in (DASHBOARD_REPO, DASHBOARD_REPO / "dashboard", DASHBOARD_REPO / "scripts"):
    _ps = str(_p)
    if _ps not in sys.path:
        sys.path.insert(0, _ps)

from post_monday_pulse import (  # type: ignore
    _fmt_target,
    _format_metric_value,
    _render_asana_goal,
    _render_live_metric,
)
from dashboard.data.metric_registry import (  # type: ignore
    get_scorecard_dept_sensitivity,
    get_scorecard_label,
)

from .rendered_row import RenderedRow
from .static_scorecard_targets import STATIC_SCORECARD_TARGETS


PHASE2_PLACEHOLDER = "\U0001F528 (Phase 2 migration)"
DATA_UNAVAILABLE_PLACEHOLDER = "\U0001F528 (data unavailable)"
SPECIAL_METRIC_NAMES = {"Demand NRR", "Pipeline Coverage", "Bill Payment Timeliness"}

# Trailing "  ·  target X" pattern that some special-override metrics embed
# inline in the body returned by _render_live_metric (e.g., Pipeline Coverage,
# which appends "· target $5.62M (2.5x)" inside its body rather than going
# through the suffix-append path). Session 3.7 splits these so deck col 1
# (Target) gets the X portion and deck col 2 (Actual) gets everything before.
_INLINE_TARGET_RE = re.compile(r"\s*·\s*target\s+(.+?)\s*$", re.IGNORECASE)


def _split_inline_target(body: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
    """Split body on inline '  ·  target X' suffix.

    Returns (actual_display, target_display). If body has no inline target,
    target_display is None and actual_display is the unchanged body.
    """
    if not body:
        return body, None
    match = _INLINE_TARGET_RE.search(body)
    if match:
        target = match.group(1).strip()
        actual = body[: match.start()].rstrip()
        return actual, target
    return body, None

# Live-function dispatch table for engineering metrics. Populated in Phase 2 by
# Engineering live wiring (out of scope for Session 2). Empty dict here is
# intentional — the cascade order test (Patch 8) verifies Step 0a precedes
# Step 0b at SOURCE level, even when the table is empty.
ENGINEERING_LIVE_METRICS: Dict[str, Callable] = {}


def _resolve_canonical_name(entry: Dict[str, Any]) -> str:
    """Real registry entries from get_scorecard_metrics_for_dept have `key` (the
    registry dict key, injected by metric_registry.py:3088). Tests sometimes
    pass `name` — accept either, prefer key (production shape)."""
    return entry.get("key") or entry.get("name") or ""


def _resolve_target_string(entry: Dict[str, Any], dept_id: str) -> Optional[str]:
    """4-step target cascade (Patch 7 wiring):

    1. Cron's _fmt_target → registry per-dept scorecard_target dict
    2. STATIC_SCORECARD_TARGETS → slash-command-owned static map for metrics
       whose target is hardcoded in dashboard page render code

    Returns the formatted target string, or None when no target is defined.
    """
    target_str = _fmt_target(entry, dept_id)
    if target_str is not None:
        return target_str

    canonical_name = _resolve_canonical_name(entry)
    static_target = STATIC_SCORECARD_TARGETS.get(canonical_name)
    if static_target is None:
        return None

    try:
        return _format_metric_value(entry, static_target)
    except Exception:
        return str(static_target)


def render_one_row(
    entry: Dict[str, Any],
    dept_id: str,
    company_metrics: Dict[str, Any],
    today,
) -> RenderedRow:
    canonical_name = _resolve_canonical_name(entry)
    sensitivity = get_scorecard_dept_sensitivity(entry, dept_id) or "public"
    display_label = get_scorecard_label(entry, dept_id, canonical_name)

    # Step 0a: ENGINEERING_LIVE_METRICS check — MUST precede Step 0b per Patch 8.
    if canonical_name in ENGINEERING_LIVE_METRICS:
        live_fn = ENGINEERING_LIVE_METRICS[canonical_name]
        try:
            actual_raw, display = live_fn(entry, dept_id, company_metrics)
            # Live functions return a single combined display string today.
            # actual_display == display, no separate target until Phase 2.
            return RenderedRow(
                metric_name=canonical_name,
                display_label=display_label,
                dept_id=dept_id,
                sensitivity=sensitivity,
                actual_raw=actual_raw,
                target_raw=None,
                status_icon="⚪",
                display=display,
                actual_display=display,
                target_display=None,
                is_phase2_placeholder=False,
                is_special_override=False,
            )
        except Exception:
            return RenderedRow(
                metric_name=canonical_name,
                display_label=display_label,
                dept_id=dept_id,
                sensitivity=sensitivity,
                actual_raw=None,
                target_raw=None,
                status_icon="⚪",
                display=DATA_UNAVAILABLE_PLACEHOLDER,
                actual_display=DATA_UNAVAILABLE_PLACEHOLDER,
                target_display=None,
                is_phase2_placeholder=False,
                is_special_override=False,
            )

    # Step 0b: needs_build → "🔨 (Phase 2 migration)" placeholder.
    if entry.get("scorecard_status") == "needs_build":
        return RenderedRow(
            metric_name=canonical_name,
            display_label=display_label,
            dept_id=dept_id,
            sensitivity=sensitivity,
            actual_raw=None,
            target_raw=None,
            status_icon="\U0001F528",
            display=PHASE2_PLACEHOLDER,
            actual_display=PHASE2_PLACEHOLDER,
            target_display=None,
            is_phase2_placeholder=True,
            is_special_override=False,
        )

    # Step 0c: asana_goal status → cron's Asana Goals API renderer.
    # Without this branch, asana_goal entries fall through to _render_live_metric
    # which returns "—  _(per-page data — Batch 3 will wire)_" because bq_key=None.
    if entry.get("scorecard_status") == "asana_goal":
        body = _render_asana_goal(entry)
        target_str = _resolve_target_string(entry, dept_id)
        target_suffix = f"  ·  target {target_str}" if target_str else ""
        return RenderedRow(
            metric_name=canonical_name,
            display_label=display_label,
            dept_id=dept_id,
            sensitivity=sensitivity,
            actual_raw=None,
            target_raw=None,
            status_icon="⚪",
            display=f"{body}{target_suffix}",
            actual_display=body,
            target_display=target_str,
            is_phase2_placeholder=False,
            is_special_override=False,
        )

    # Step 1-4: cron's _render_live_metric handles the full live cascade —
    # special overrides, sales-per-page, scope=both, single-value.
    body = _render_live_metric(entry, dept_id, company_metrics, canonical_name)
    skip_default_target = isinstance(body, str) and "\x00SKIP_TARGET" in body
    if skip_default_target:
        body = body.replace("\x00SKIP_TARGET", "")
    target_str = None if skip_default_target else _resolve_target_string(entry, dept_id)
    target_suffix = f"  ·  target {target_str}" if target_str else ""
    display = f"{body}{target_suffix}"

    # Session 3.7: split actual vs target for the deck's per-column layout.
    # Two cases produce a target_display:
    #   (a) target_str is non-None — the cascade resolved a target via
    #       registry/static map, and the suffix appends it to display.
    #   (b) target_str is None but body has an inline "  ·  target X" suffix
    #       (special-overrides like Pipeline Coverage embed target this way).
    if target_str is not None:
        actual_display = body
        target_display: Optional[str] = target_str
    else:
        actual_display, target_display = _split_inline_target(body)

    return RenderedRow(
        metric_name=canonical_name,
        display_label=display_label,
        dept_id=dept_id,
        sensitivity=sensitivity,
        actual_raw=None,
        target_raw=None,
        status_icon="⚪",
        display=display,
        actual_display=actual_display,
        target_display=target_display,
        is_phase2_placeholder=False,
        is_special_override=(canonical_name in SPECIAL_METRIC_NAMES),
    )
