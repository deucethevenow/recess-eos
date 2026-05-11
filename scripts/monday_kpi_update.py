"""/monday-kpi-update — slash command entry point.

v3.8 Patches 1, 2, 5, 10, 11 wired together:
  - Patch 1: pin company_metrics + today ONCE per run; render every metric via
             render_one_row; all surface writers consume RenderedRow.display.
  - Patch 2: mandatory sensitivity confirmation gate before any write.
  - Patch 5: pre-flight runtime checks (rocks available, deck table rows, today logged).
  - Patch 10: title-based DEPT_SLIDE_MAP resolver (drift-resilient).
  - Patch 11: cron transition — Week 1 verify defaults to test channel.

Surface writers (deck_writer, slack_writer, leadership_doc_writer) are wired
in Session 3. Each consumes RenderedRow.display so cross-output parity is
enforced by the contract.

Phase 11 cron transition (decided 2026-05-04):
  - Week 1+ verify: DEFAULT_SLACK_CHANNEL targets the test channel
    (#kpi-dashboard-notifications, C0AN5N36HDM). Run manually each Monday;
    compare output against the live KPI dashboard for parity.
  - Cut-over criterion: 2 consecutive clean Mondays where slash-command output
    matches the dashboard within tolerance.
  - Post-cutover: change DEFAULT_SLACK_CHANNEL to PROD_SLACK_CHANNEL and pause
    the existing weekly-digest-monday cron via:
      gcloud scheduler jobs pause weekly-digest-monday --location us-central1

Defaults per memory rule "easier to downgrade than leak":
  - deck:           max_sensitivity = "public"      (all-hands audience)
  - Slack:          max_sensitivity = "public"      (company-wide channel)
  - leadership doc: max_sensitivity = "leadership"  (dept leads only)
"""
from __future__ import annotations

import os
import sys
from datetime import date as _date
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, Optional

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

from lib.dept_slide_map import (  # noqa: E402
    resolve_dept_rocks_slide_map,
    resolve_dept_slide_map,
)
from lib.failure_alert import emit_failure_alert  # noqa: E402
from lib.founders_preread import build_payloads_for_founders_preread  # noqa: E402
from lib.metric_payloads import MetricPayload  # noqa: E402
from lib.preflight import PreflightError, run_preflight  # noqa: E402
from lib.rendered_row import RenderedRow  # noqa: E402
from lib.scorecard_renderer import (  # noqa: E402
    render_one_row,
    render_rock_or_project_row,
)


DEFAULT_DECK_ID = "1kjg1ObSO1l15_R82w6hgQNOz8YYk3oUXPllBs-eGhow"

# Phase 11 channel routing — see module docstring for cut-over protocol.
PROD_SLACK_CHANNEL = "C0AQP3WH7AB"  # #recess-goals-kpis (post-cutover target)
VERIFY_SLACK_CHANNEL = "C0AN5N36HDM"  # #kpi-dashboard-notifications (Week 1+ verify)
DEFAULT_SLACK_CHANNEL = VERIFY_SLACK_CHANNEL  # Cut-over: switch to PROD_SLACK_CHANNEL


# --------------------------------------------------------------------------- #
# Phase B+ — Founders pre-read adapter wiring                                 #
# --------------------------------------------------------------------------- #


_STATUS_3STATE_TO_ICON = {
    "on_track": "\U0001F7E2",   # 🟢
    "at_risk":  "\U0001F7E1",   # 🟡
    "off_track": "\U0001F534",  # 🔴
}
# None and unexpected values fall through to "⚪" via dict.get(..., "⚪") default.


def _payload_to_rendered_row(payload: MetricPayload) -> RenderedRow:
    """Shim — convert a MetricPayload to a RenderedRow for backward compat with
    deck/Slack/leadership-doc writers that still consume RenderedRow downstream.

    Phase B+ scaffolding. Phase C+E moved `target_display` formatting onto
    MetricPayload itself, so this shim no longer reaches into private
    formatters — it just forwards `payload.target_display` through.
    Migrating writers off RenderedRow remains future work; this shim
    disappears when that happens.
    """
    return RenderedRow(
        metric_name=payload.metric_name,
        display_label=payload.config_key or payload.metric_name,
        dept_id=payload.dept_id,
        sensitivity=payload.sensitivity,
        actual_raw=payload.raw_value,
        target_raw=payload.target,
        status_icon=_STATUS_3STATE_TO_ICON.get(payload.status_3state, "⚪"),
        display=payload.display_value,
        actual_display=payload.display_value,
        target_display=payload.target_display,
        trend_display=None,
        is_phase2_placeholder=(payload.availability_state == "needs_build"),
        is_special_override=False,
    )


def _build_founders_rendered_rows(
    company_metrics: Dict[str, Any],
    snapshot_timestamp: Optional[str] = None,
) -> list:
    """Phase B+ — produce RenderedRow list for the founders dept via the
    canonical MetricPayload pipeline. Loads the 'founders' meeting from
    config/recess_os.yml, calls build_payloads_for_founders_preread, then
    runs each payload through _payload_to_rendered_row.

    Today this branch isn't exercised in production (DEPT_METRIC_ORDER excludes
    'founders' — the founders pre-read is a Phase 3 placeholder in
    recess_os_daily.sh). The wiring exists so Phase 3 has a single blessed
    code path: any future founders pre-read MUST route through the adapter,
    not introduce a parallel render_one_row-based pipeline. Test #7 in
    test_monday_update_surface_parity.py enforces that structurally.
    """
    import yaml

    config_path = Path(__file__).resolve().parent.parent / "config" / "recess_os.yml"
    try:
        cfg = yaml.safe_load(config_path.read_text())
    except (FileNotFoundError, yaml.YAMLError) as e:
        emit_failure_alert(
            surface="founders_preread_yaml_load",
            detail=f"failed to load {config_path}; founders pre-read returns empty",
            exc=e,
        )
        return []

    founders_meeting = next(
        (m for m in cfg.get("meetings", []) if m.get("id") == "founders"),
        None,
    )
    if not founders_meeting:
        return []

    ts = snapshot_timestamp or company_metrics.get("snapshot_timestamp", "")
    payloads = build_payloads_for_founders_preread(founders_meeting, company_metrics, ts)
    return [_payload_to_rendered_row(p) for p in payloads]


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
    leadership_doc_id: Optional[str] = None,
    skip_deck: bool = False,
    skip_rocks_deck: bool = False,
    skip_slack: bool = False,
    fetch_presentation: Optional[Callable[[str], Dict[str, Any]]] = None,
    fetch_table_row_count: Optional[Callable[[str, int], Optional[int]]] = None,
    slides_service: Any = None,
    docs_service: Any = None,
    slack_post_fn: Optional[Callable[..., str]] = None,
    firestore_client: Any = None,
    input_fn: Callable[[str], str] = input,
) -> Dict[str, Dict[str, Any]]:
    """Run the slash command end-to-end.

    The sensitivity gate is non-bypassable. Tests inject `input_fn=lambda _: "y"`
    rather than skipping the gate — the only legitimate way to proceed is by
    answering 'y' to the explicit prompt. This intentionally has no escape
    hatch (C5 fix from review): the Apr 29 leak post-mortem in
    feedback_decision_sensitivity_gate.md established that any bypass parameter
    becomes a foot-gun.

    Session 3 NIT-3: deck integration is opt-in. With `skip_deck=False` (default),
    `fetch_presentation`, `fetch_table_row_count`, and `slides_service` are all
    required — main() raises ValueError early if any is None. With
    `skip_deck=True`, the deck step is bypassed entirely and the deck-related
    preflight checks are silenced.

    Surface writer dispatch order:
        1. Deck (Slides API) — if not skip_deck
        2. Slack — if not skip_slack
        3. Leadership doc — if include_leadership_doc
    Each surface has its own try/except wrapper that emits a failure alert and
    continues to the next surface. Slack idempotency uses a Firestore marker
    keyed on run_date. Deck idempotency relies on deleteText+insertText pairing
    inside lib.idempotency.write_cell.
    """
    if not skip_deck:
        missing_deck = [
            name
            for name, val in (
                ("fetch_presentation", fetch_presentation),
                ("fetch_table_row_count", fetch_table_row_count),
                ("slides_service", slides_service),
            )
            if val is None
        ]
        if missing_deck:
            raise ValueError(
                "skip_deck=False requires Slides API bindings: "
                f"missing {missing_deck}. Pass them as keyword args, or set "
                "skip_deck=True to bypass deck integration entirely."
            )
    if include_leadership_doc and (docs_service is None or leadership_doc_id is None):
        raise ValueError(
            "include_leadership_doc=True requires both docs_service and "
            "leadership_doc_id keyword args."
        )

    today = _date.today()

    company_metrics = get_company_metrics()

    rock_data = get_rock_project_progress() or {"available": False}
    rocks_by_dept = _bucket_rocks_by_dept(rock_data)

    dept_to_slide = (
        resolve_dept_slide_map(deck_id, fetch_presentation=fetch_presentation)
        if not skip_deck
        else {}
    )
    dept_to_rocks_slide = (
        resolve_dept_rocks_slide_map(deck_id, fetch_presentation=fetch_presentation)
        if (not skip_deck and not skip_rocks_deck)
        else {}
    )

    rendered_per_dept: Dict[str, Dict[str, Any]] = {}
    rendered_rocks_per_dept: Dict[str, Dict[str, Any]] = {}
    for dept_id in DEPT_METRIC_ORDER.keys():
        entries = get_scorecard_metrics_for_dept(dept_id) or []
        rocks_for_dept = rocks_by_dept.get(dept_id, {})
        if not entries and not rocks_for_dept.get("rocks") and not rocks_for_dept.get("projects"):
            continue
        # Phase B+ — founders pre-read consumes the canonical MetricPayload
        # pipeline (closes the dual-pipeline loophole flagged by Phase 0
        # reviewers). Other depts continue on render_one_row until Phase C+E
        # migrates them. Today this branch is forward-looking infrastructure:
        # DEPT_METRIC_ORDER excludes 'founders', so the branch doesn't fire
        # in current runs — the founders pre-read is a Phase 3 placeholder
        # in recess_os_daily.sh. When Phase 3 lands, this is the only blessed
        # code path; Test #7 enforces structurally.
        if dept_id == "founders":
            rows = _build_founders_rendered_rows(company_metrics)
        else:
            rows = [render_one_row(e, dept_id, company_metrics, today) for e in entries]
        rendered_per_dept[dept_id] = {
            "scorecard_rows": rows,
            "rocks_section": rocks_for_dept,
            "slide_idx": dept_to_slide.get(dept_id),
        }
        # Build a parallel "scorecard_rows" payload from rocks+projects for
        # the rocks deck writer. The deck writer consumes any payload with a
        # `scorecard_rows` list + `slide_idx`, so we reuse the same shape.
        rock_rows = [
            render_rock_or_project_row(item, dept_id)
            for item in (rocks_for_dept.get("rocks") or [])
        ]
        project_rows = [
            render_rock_or_project_row(item, dept_id)
            for item in (rocks_for_dept.get("projects") or [])
        ]
        if rock_rows or project_rows:
            rendered_rocks_per_dept[dept_id] = {
                "scorecard_rows": rock_rows + project_rows,
                "slide_idx": dept_to_rocks_slide.get(dept_id),
            }

    run_preflight(
        today=today,
        company_metrics=company_metrics,
        rock_data=rock_data,
        rendered_per_dept=rendered_per_dept,
        deck_id=deck_id,
        fetch_table_row_count=fetch_table_row_count if not skip_deck else None,
        skip_deck=skip_deck,
        rendered_rocks_per_dept=rendered_rocks_per_dept,
        skip_rocks_deck=skip_rocks_deck,
    )

    confirm_sensitivity_gate(rendered_per_dept, input_fn=input_fn)

    # ---- Surface writers (Session 3) -------------------------------------- #
    # Each surface is independently wrapped: a failure on the deck does not
    # block Slack, and a Slack failure does not block leadership-doc.

    if not skip_deck:
        try:
            from lib.deck_writer import apply_via_slides_api  # noqa: E402
            apply_via_slides_api(
                rendered_per_dept=rendered_per_dept,
                max_sensitivity="public",
                slides_service=slides_service,
                presentation_id=deck_id,
            )
        except Exception as e:  # noqa: BLE001
            emit_failure_alert(
                surface="deck",
                detail="apply_via_slides_api failed at the top level (not per-slide).",
                exc=e,
            )

    if not skip_deck and not skip_rocks_deck and rendered_rocks_per_dept:
        try:
            from lib.deck_writer import apply_via_slides_api  # noqa: E402
            # max_sensitivity="leadership" because rocks/projects are typically
            # not appropriate for public-channel rendering (they reflect ongoing
            # internal initiatives). The deck audience IS leadership-tier,
            # so this is the right scope.
            apply_via_slides_api(
                rendered_per_dept=rendered_rocks_per_dept,
                max_sensitivity="leadership",
                slides_service=slides_service,
                presentation_id=deck_id,
            )
        except Exception as e:  # noqa: BLE001
            emit_failure_alert(
                surface="deck_rocks",
                detail="apply_via_slides_api (rocks) failed at the top level.",
                exc=e,
            )

    if not skip_slack:
        try:
            from lib.slack_writer import post_pulse  # noqa: E402
            post_pulse(
                rendered_per_dept=rendered_per_dept,
                rocks_by_dept=rocks_by_dept,
                channel_id=slack_channel,
                run_date=today,
                max_sensitivity="public",
                post_fn=slack_post_fn,
                firestore_client=firestore_client,
            )
        except Exception as e:  # noqa: BLE001
            emit_failure_alert(
                surface="slack",
                detail="post_pulse failed.",
                exc=e,
            )

    if include_leadership_doc:
        try:
            from lib.leadership_doc_writer import apply_to_leadership_doc  # noqa: E402
            apply_to_leadership_doc(
                rendered_per_dept=rendered_per_dept,
                rocks_by_dept=rocks_by_dept,
                doc_id=leadership_doc_id,
                docs_service=docs_service,
                max_sensitivity="leadership",
            )
        except Exception as e:  # noqa: BLE001
            emit_failure_alert(
                surface="leadership_doc",
                detail="apply_to_leadership_doc failed.",
                exc=e,
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
