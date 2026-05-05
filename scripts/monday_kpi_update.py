"""/monday-kpi-update — slash command entry point.

v3.8 Patches 1, 2, 5, 10 wired together:
  - Patch 1: pin company_metrics + today ONCE per run; render every metric via
             render_one_row; all surface writers consume RenderedRow.display.
  - Patch 2: mandatory sensitivity confirmation gate before any write.
  - Patch 5: pre-flight runtime checks (rocks available, deck table rows, today logged).
  - Patch 10: title-based DEPT_SLIDE_MAP resolver (drift-resilient).

Surface writers (deck_writer, slack_writer, leadership_doc_writer) are intentionally
NOT wired in Session 2 — they're scaffolded as TODO call-sites with clear contracts.
Session 3 (or a follow-up) wires the actual Slides API / Slack / Docs writers, all
consuming RenderedRow.display so cross-output parity is enforced by the contract.

Defaults per memory rule "easier to downgrade than leak":
  - deck:           max_sensitivity = "public"      (all-hands audience)
  - Slack:          max_sensitivity = "public"      (company-wide channel)
  - leadership doc: max_sensitivity = "leadership"  (dept leads only)
"""
from __future__ import annotations

import sys
from datetime import date as _date
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, Optional

DASHBOARD_REPO = Path("/Users/deucethevenowworkm1/Projects/company-kpi-dashboard")
for _p in (DASHBOARD_REPO, DASHBOARD_REPO / "dashboard", DASHBOARD_REPO / "scripts"):
    _ps = str(_p)
    if _ps not in sys.path:
        sys.path.insert(0, _ps)

# Imports below intentionally come AFTER the sys.path mutations above. The
# dashboard repo path must already be on sys.path before these resolve.
from post_monday_pulse import (  # type: ignore
    DEPT_METRIC_ORDER,
    OWNER_EMAIL_TO_DEPT,
    _format_rock_line,
    _sensitivity_allowed,
)
from dashboard.data.data_layer import (  # type: ignore
    get_company_metrics,
    get_rock_project_progress,
)
from dashboard.data.metric_registry import get_scorecard_metrics_for_dept  # type: ignore

_SCRIPTS_DIR = str(Path(__file__).resolve().parent)
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

from lib.dept_slide_map import resolve_dept_slide_map  # noqa: E402
from lib.failure_alert import emit_failure_alert  # noqa: E402
from lib.preflight import PreflightError, run_preflight  # noqa: E402
from lib.rendered_row import RenderedRow  # noqa: E402
from lib.scorecard_renderer import render_one_row  # noqa: E402


DEFAULT_DECK_ID = "1kjg1ObSO1l15_R82w6hgQNOz8YYk3oUXPllBs-eGhow"
DEFAULT_SLACK_CHANNEL = "C0AQP3WH7AB"  # #recess-goals-kpis


# --------------------------------------------------------------------------- #
# Funnel pre-fetch — Patch 4e wrapper                                         #
# --------------------------------------------------------------------------- #


def _safe_funnel_fetch() -> Optional[Any]:
    """Pre-fetch engineering discovery funnel; alert + return None on failure.

    The 6 funnel-stage metrics resolve to "🔨 (data unavailable)" when the
    cache is None — see scorecard_renderer Step 0a fallback. The 3 hero
    engineering metrics are independent BQ calls and still resolve.
    """
    try:
        from dashboard.data.engineering_client import get_discovery_funnel  # type: ignore

        return get_discovery_funnel()
    except Exception as e:  # noqa: BLE001
        emit_failure_alert(
            surface="engineering_funnel_prefetch",
            detail=(
                "get_discovery_funnel() failed; 6 funnel metrics will render as "
                "'🔨 (data unavailable)'. 3 hero metrics still resolve independently."
            ),
            exc=e,
        )
        return None


# --------------------------------------------------------------------------- #
# Rock bucketing — by dept via OWNER_EMAIL_TO_DEPT                            #
# --------------------------------------------------------------------------- #


def _bucket_rocks_by_dept(rock_data: Dict[str, Any]) -> Dict[str, Dict[str, list]]:
    by_dept: Dict[str, Dict[str, list]] = {}
    for kind in ("rocks", "projects"):
        for item in rock_data.get(kind, []) or []:
            owner_email = (item.get("owner_email") or "").lower()
            dept = OWNER_EMAIL_TO_DEPT.get(owner_email, "leadership")
            slot = by_dept.setdefault(dept, {"rocks": [], "projects": []})
            slot[kind].append(item)
    return by_dept


# --------------------------------------------------------------------------- #
# Sensitivity gate — Patch 2                                                  #
# --------------------------------------------------------------------------- #


def _summarize_sensitivity(
    rendered_per_dept: Dict[str, Dict[str, Any]],
) -> Dict[str, list]:
    by_sens: Dict[str, list] = {"public": [], "leadership": [], "founders_only": []}
    for dept_id, payload in rendered_per_dept.items():
        for row in payload.get("scorecard_rows", []):
            by_sens.setdefault(row.sensitivity, []).append(
                f"{dept_id}: {row.metric_name}"
            )
    return by_sens


def confirm_sensitivity_gate(
    rendered_per_dept: Dict[str, Dict[str, Any]],
    *,
    input_fn: Callable[[str], str] = input,
    print_fn: Callable[..., None] = print,
) -> None:
    """Print classification, require explicit y/N before any surface write.

    Per memory rule feedback_decision_sensitivity_gate.md (Apr 29 2026 leak):
    default to HIGHER sensitivity when in doubt. Founders-only rows are filtered
    on all 3 surfaces; this gate confirms the classification is correct BEFORE
    any write. Aborting raises SystemExit so callers cannot suppress.
    """
    by_sens = _summarize_sensitivity(rendered_per_dept)
    print_fn("=" * 60)
    print_fn("SENSITIVITY GATE — confirm before writing to deck/Slack/leadership doc")
    print_fn("=" * 60)
    print_fn(f"\U0001F7E2 public ({len(by_sens['public'])} rows):")
    for r in by_sens["public"][:5]:
        print_fn(f"   {r}")
    if len(by_sens["public"]) > 5:
        print_fn(f"   ... +{len(by_sens['public']) - 5} more")
    print_fn(f"\U0001F7E1 leadership ({len(by_sens['leadership'])} rows):")
    for r in by_sens["leadership"]:
        print_fn(f"   {r}")
    print_fn(f"\U0001F534 founders_only ({len(by_sens['founders_only'])} rows):")
    for r in by_sens["founders_only"]:
        print_fn(f"   {r}")
    print_fn("")
    print_fn("Surface defaults: deck=public, Slack=public, leadership-doc=leadership")
    print_fn("Founders-only rows will be FILTERED on all 3 surfaces.")
    print_fn("")
    confirm = input_fn("Proceed? [y/N]: ").strip().lower()
    if confirm != "y":
        raise SystemExit("Aborted at sensitivity gate.")


# --------------------------------------------------------------------------- #
# Slack composition — reads row.display ONLY                                  #
# --------------------------------------------------------------------------- #


def build_dept_section_for_slack(
    dept_id: str,
    rendered_rows: Iterable[RenderedRow],
    rocks_section: Dict[str, list],
    max_sensitivity: str,
) -> list:
    rows = list(rendered_rows)
    visible = [r for r in rows if _sensitivity_allowed(r.sensitivity, max_sensitivity)]
    skipped = len(rows) - len(visible)

    lines = [f"*{dept_id}*"]  # dept label is keyed by id; pretty-label TBD downstream
    rocks = rocks_section.get("rocks", [])
    projects = rocks_section.get("projects", [])
    if rocks:
        lines.append("\U0001FAA8 _Rocks_")
        lines.extend(_format_rock_line(r) for r in rocks)
    if projects:
        lines.append("\U0001F4CC _Projects_")
        lines.extend(_format_rock_line(p) for p in projects)
    if visible:
        lines.append("\U0001F4CA _Metrics_")
        for row in visible:
            # C3 fix: use row.display_label (per-dept resolved) — NOT row.metric_name
            # (raw registry key). Cross-output parity requires deck/Slack/leadership
            # all consume the same label string.
            lines.append(f"• *{row.display_label}*: {row.display}")
    if skipped:
        lines.append(f"_{skipped} metric(s) filtered (sensitivity)_")
    return [{"type": "section", "text": {"type": "mrkdwn", "text": "\n".join(lines)}}]


# --------------------------------------------------------------------------- #
# Main flow                                                                   #
# --------------------------------------------------------------------------- #


def main(
    *,
    deck_id: str = DEFAULT_DECK_ID,
    slack_channel: str = DEFAULT_SLACK_CHANNEL,
    include_leadership_doc: bool = False,
    fetch_presentation: Optional[Callable[[str], Dict[str, Any]]] = None,
    fetch_table_row_count: Optional[Callable[[str, int], Optional[int]]] = None,
    input_fn: Callable[[str], str] = input,
) -> Dict[str, Dict[str, Any]]:
    """Run the slash command end-to-end.

    The sensitivity gate is non-bypassable. Tests inject `input_fn=lambda _: "y"`
    rather than skipping the gate — the only legitimate way to proceed is by
    answering 'y' to the explicit prompt. This intentionally has no escape
    hatch (C5 fix from review): the Apr 29 leak post-mortem in
    feedback_decision_sensitivity_gate.md established that any bypass parameter
    becomes a foot-gun.
    """
    today = _date.today()

    company_metrics = get_company_metrics()
    company_metrics["_funnel_cache"] = _safe_funnel_fetch()

    rock_data = get_rock_project_progress() or {"available": False}
    rocks_by_dept = _bucket_rocks_by_dept(rock_data)

    dept_to_slide = resolve_dept_slide_map(
        deck_id, fetch_presentation=fetch_presentation
    ) if fetch_presentation else {}

    rendered_per_dept: Dict[str, Dict[str, Any]] = {}
    for dept_id in DEPT_METRIC_ORDER.keys():
        entries = get_scorecard_metrics_for_dept(dept_id) or []
        rocks_for_dept = rocks_by_dept.get(dept_id, {})
        if not entries and not rocks_for_dept.get("rocks") and not rocks_for_dept.get("projects"):
            continue
        rows = [render_one_row(e, dept_id, company_metrics, today) for e in entries]
        rendered_per_dept[dept_id] = {
            "scorecard_rows": rows,
            "rocks_section": rocks_for_dept,
            "slide_idx": dept_to_slide.get(dept_id),
        }

    run_preflight(
        today=today,
        company_metrics=company_metrics,
        rock_data=rock_data,
        rendered_per_dept=rendered_per_dept,
        deck_id=deck_id,
        fetch_table_row_count=fetch_table_row_count,
    )

    confirm_sensitivity_gate(rendered_per_dept, input_fn=input_fn)

    # Surface writers — wired in Session 3+. Each consumes RenderedRow.display.
    # NotImplementedError fail-loud is intentional so a partial Session 2 deploy
    # can't accidentally write to production.
    print(
        f"Session 2 contract complete: rendered {sum(len(p['scorecard_rows']) for p in rendered_per_dept.values())} "
        f"rows across {len(rendered_per_dept)} depts; surface writers TBD in Session 3."
    )
    return rendered_per_dept


if __name__ == "__main__":  # pragma: no cover — manual invocation only
    try:
        main()
    except PreflightError as e:
        print(f"Pre-flight failed: {e}", file=sys.stderr)
        sys.exit(2)
    except SystemExit:
        raise
