"""render_one_row — the single rendering function all surface writers consume.

Per v3.8 Patch 1 cascade order:
  Step 0a: needs_build → "🔨 (Phase 2 migration)" placeholder.
  Step 0b: asana_goal status → cron's _render_asana_goal (Asana Goals API path).
  Step 1-4: existing v3.5 cascade — handled by cron's _render_live_metric
            (special overrides, sales-per-page, scope=both, single value).

Cron parity divergences (deliberate):
  - Cron's needs_build placeholder = "🔨 Needs Build" (post_monday_pulse.py:933).
    Slash command uses "🔨 (Phase 2 migration)" per v3.8 plan. Documented for
    cut-over: cron and slash command will produce different placeholder text
    until cron is retired (Session 3 / Patch 11).

Target resolution (3-step cascade, Firestore-first per 2026-05-19 architecture):
  1. Cron's _fmt_target → entry["scorecard_target"][dept_id]  (per-dept override)
  2. Cron's _fmt_target → entry["target_key"] → company_metrics[target_key]
     (Firestore scalar merged into COMPANY_METRICS by data_layer)
  3. STATIC_SCORECARD_TARGETS  (legacy fallback — slash-command-owned 18-key
     map for metrics whose targets were hardcoded in dashboard render code;
     migrating to Firestore in Phase 1.5).
"""
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

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

# Deploy coupling: in Cloud Run, post_monday_pulse.py is staged from
# _dashboard_src/ (gitignored, manually rsync'd before each Dockerfile.cron
# build). Changes to _fmt_target signature here MUST be matched by a fresh
# `_dashboard_src/` stage before deploying, or the container ImportError-equivalent
# is a runtime TypeError on the next pulse. Locally, the path injection above
# points at the live dashboard repo so dev/test sees the latest signature.
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


def _resolve_canonical_name(entry: Dict[str, Any]) -> str:
    """Real registry entries from get_scorecard_metrics_for_dept have `key` (the
    registry dict key, injected by metric_registry.py:3088). Tests sometimes
    pass `name` — accept either, prefer key (production shape)."""
    return entry.get("key") or entry.get("name") or ""


def _resolve_target_string(
    entry: Dict[str, Any],
    dept_id: str,
    company_metrics: Optional[Dict[str, Any]] = None,
) -> Optional[str]:
    """Resolve a target string for one metric/dept. 3-step cascade — steps
    1 & 2 are delegated to _fmt_target → get_scorecard_target (dashboard repo);
    step 3 (STATIC fallback) is the only branch visible here.

    1. (via _fmt_target) entry["scorecard_target"][dept_id]   — per-dept override
    2. (via _fmt_target) company_metrics[entry["target_key"]] — caller-hydrated
                                                                (Firestore via
                                                                data_layer)
    3. STATIC_SCORECARD_TARGETS[canonical_name]               — legacy fallback;
                                                                Phase 1.5 target

    company_metrics is optional; step 2 is skipped when None.
    Returns the formatted target string, or None when no target is defined.
    """
    target_str = _fmt_target(entry, dept_id, company_metrics)
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


# --------------------------------------------------------------------------- #
# Rocks/Projects rendering — Session 4                                        #
# --------------------------------------------------------------------------- #
#
# `get_rock_project_progress()` returns dicts with:
#   name, owner_name, project_type, status, completion_percent (0-100),
#   task_count (int or None), asana_project_id.
#
# It does NOT include due_date today, so we use completion-only status
# thresholds (matching cron's _format_rock_line):
#   ≥ 66% → 🟢 On-track
#   ≥ 33% → 🟡 At-risk
#   <  33% → 🔴 Off-track
#
# When task_count is present, Actual is "X% (Y tasks)"; otherwise "X%".
# Trend always shows "Owner: <name>".


_ROCK_STATUS_THRESHOLDS = (
    (66.0, "\U0001F7E2", "On-track"),
    (33.0, "\U0001F7E1", "At-risk"),
    (0.0, "\U0001F534", "Off-track"),
)


def _rock_status(pct: float) -> tuple:
    """Return (icon, label) for a completion percentage."""
    for threshold, icon, label in _ROCK_STATUS_THRESHOLDS:
        if pct >= threshold:
            return icon, label
    return "\U0001F534", "Off-track"  # defensive fallback


def render_rock_or_project_row(
    item: Dict[str, Any],
    dept_id: str,
    sensitivity: str = "leadership",
) -> RenderedRow:
    """Render one rock or project as a RenderedRow for the deck's rocks slide.

    Field mapping for the deck's 5-column shape:
      Metric  → name
      Target  → "100%" (rocks always target 100% complete)
      Actual  → "{pct:.0f}% ({task_count} tasks)" or "{pct:.0f}%"
      Status  → 🟢/🟡/🔴 icon + " " + label (e.g., "🟢 On-track")
      Trend   → "Owner: {owner_name}"

    Note: deck_writer reads `display_label` for col 0, `target_display` for
    col 1, `actual_display` for col 2, `status_icon` for col 3 — and now
    Session 4 also reads a new field `trend_display` for col 4. The combined
    `display` field (used by Slack/leadership-doc) is "{name} — {pct:.0f}%
    ({owner_name})" so the existing Slack rock formatter is unaffected.

    Sensitivity defaults to "leadership" because rocks/projects are typically
    not public-channel content. Caller can override.
    """
    name = (item.get("name") or "Unnamed").strip()
    owner = (item.get("owner_name") or "Unassigned").strip()
    pct_raw = item.get("completion_percent")
    try:
        pct = float(pct_raw) if pct_raw is not None else 0.0
    except (TypeError, ValueError):
        pct = 0.0
    task_count = item.get("task_count")

    icon, label = _rock_status(pct)

    if task_count:
        try:
            actual_str = f"{pct:.0f}% ({int(task_count)} tasks)"
        except (TypeError, ValueError):
            actual_str = f"{pct:.0f}%"
    else:
        actual_str = f"{pct:.0f}%"

    target_str = "100%"
    status_str = f"{icon} {label}"
    trend_str = f"Owner: {owner}"

    combined_display = f"{icon} *{name}* — {pct:.0f}% _({owner})_"

    return RenderedRow(
        metric_name=name,
        display_label=name,
        dept_id=dept_id,
        sensitivity=sensitivity,
        actual_raw=pct,
        target_raw=100.0,
        status_icon=status_str,  # Session 4: now includes label not just icon
        display=combined_display,
        actual_display=actual_str,
        target_display=target_str,
        trend_display=trend_str,  # Session 4: deck col 4 (Trend) — owner
        is_phase2_placeholder=False,
        is_special_override=False,
    )


def render_one_row(
    entry: Dict[str, Any],
    dept_id: str,
    company_metrics: Dict[str, Any],
    today,
) -> RenderedRow:
    canonical_name = _resolve_canonical_name(entry)
    sensitivity = get_scorecard_dept_sensitivity(entry, dept_id) or "public"
    display_label = get_scorecard_label(entry, dept_id, canonical_name)

    # Step 0a: needs_build → "🔨 (Phase 2 migration)" placeholder.
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
            trend_display=None,
            is_phase2_placeholder=True,
            is_special_override=False,
        )

    # Step 0b: asana_goal status → cron's Asana Goals API renderer.
    # Without this branch, asana_goal entries fall through to _render_live_metric
    # which returns "—  _(per-page data — Batch 3 will wire)_" because bq_key=None.
    if entry.get("scorecard_status") == "asana_goal":
        body = _render_asana_goal(entry)
        target_str = _resolve_target_string(entry, dept_id, company_metrics)
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
            trend_display=None,
            is_phase2_placeholder=False,
            is_special_override=False,
        )

    # Step 1-4: cron's _render_live_metric handles the full live cascade —
    # special overrides, sales-per-page, scope=both, single-value.
    body = _render_live_metric(entry, dept_id, company_metrics, canonical_name)
    skip_default_target = isinstance(body, str) and "\x00SKIP_TARGET" in body
    if skip_default_target:
        body = body.replace("\x00SKIP_TARGET", "")
    target_str = None if skip_default_target else _resolve_target_string(entry, dept_id, company_metrics)
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
        trend_display=None,
        is_phase2_placeholder=False,
        is_special_override=(canonical_name in SPECIAL_METRIC_NAMES),
    )
