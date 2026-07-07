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

Surface visibility (P2.3, Metric Routing): every writer filters through the
resolver's is_visible on its own surface — deck/slack (ceiling public), doc
(ceiling leadership) — so a routing toggle can never widen a metric past its
registry ceiling ("easier to downgrade than leak" now enforced structurally).
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
    OWNER_EMAIL_TO_DEPT,
    _format_rock_line,
)
from dashboard.data.data_layer import (  # type: ignore
    get_company_metrics,
    get_rock_project_progress,
)
from data.metric_routing import (  # type: ignore
    dept_rows,
    is_visible,
    rock_visible,
    validate_routing,
)
from data.routing_manager import load_routing  # type: ignore  (errors propagate to callers)

_SURFACES = ("slack", "deck", "doc", "l10")


def _load_registry_for_routing() -> Dict[str, Any]:
    """The resolver needs the registry dict (ceilings). Wrapped for testability."""
    from dashboard.data.metric_registry import METRIC_REGISTRY  # type: ignore

    return METRIC_REGISTRY

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

    Today this branch isn't exercised in production (the founders routing rows
    seed all-False on every surface, so main()'s all-dark dept skip rule
    excludes founders — the founders pre-read is a Phase 3 placeholder in
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


def _bucket_rocks_by_dept(
    rock_data: Dict[str, Any],
    routing: Dict[str, Any],
    surface: str,
) -> Dict[str, Dict[str, list]]:
    """Group rocks/projects by dept, filtered for ONE surface via rock_visible.

    P2.3: the routing filter lives HERE — upstream, while `asana_project_id`
    is still on each item (RenderedRow drops it). Rock toggles are per-surface,
    so each surface gets its own bucket; unknown GIDs default ON.
    """
    by_dept: Dict[str, Dict[str, list]] = {}
    for kind in ("rocks", "projects"):
        for item in rock_data.get(kind, []) or []:
            if not rock_visible(routing, item.get("asana_project_id"), surface):
                continue
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
    routing: Dict[str, Any],
    registry: Dict[str, Any],
) -> list:
    rows = list(rendered_rows)
    # P2.3: visibility = the resolver on the "slack" surface (toggle AND ceiling).
    visible = [
        r for r in rows
        if is_visible(routing, r.dept_id, r.metric_name, "slack", registry)
    ]
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

    # Routing store loads ONCE per run, BEFORE any render/write. Unavailable or
    # malformed routing ABORTS the whole run (fail-loud contract: a Monday
    # update must never silently post everything).
    routing = load_routing()
    registry = _load_registry_for_routing()
    orphans = validate_routing(routing, registry)
    if orphans:
        print(
            f"[monday-kpi-update] WARNING: routing rows for metrics no longer in "
            f"the registry (rendered nowhere; prune via the Metric Routing page): {orphans}",
            file=sys.stderr,
        )

    company_metrics = get_company_metrics()

    rock_data = get_rock_project_progress() or {"available": False}
    # Rock toggles are per-surface: each surface consumes its own bucket,
    # filtered upstream while asana_project_id is still on the items.
    rocks_by_dept_slack = _bucket_rocks_by_dept(rock_data, routing, "slack")
    rocks_by_dept_doc = _bucket_rocks_by_dept(rock_data, routing, "doc")
    rocks_by_dept_deck = _bucket_rocks_by_dept(rock_data, routing, "deck")

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
    # P2.3: the dept loop walks the ROUTING store — membership + row order both
    # come from the doc (store row order == display order on every surface).
    # Dept SECTION order comes from SCORECARD_DEPT_NAMES (canonical display
    # order) — Firestore maps deserialize alphabetically, never trust that.
    from dashboard.data.metric_registry import SCORECARD_DEPT_NAMES  # type: ignore

    routing_depts = routing.get("metrics") or {}
    ordered_depts = [d for d in SCORECARD_DEPT_NAMES if d in routing_depts]
    ordered_depts += [d for d in routing_depts if d not in SCORECARD_DEPT_NAMES]
    for dept_id in ordered_depts:
        routing_rows = dept_rows(routing, dept_id)
        entries = [
            {**registry[r["metric"]], "key": r["metric"]}
            for r in routing_rows
            if r["metric"] in registry  # orphans warned above; never rendered
        ]
        rocks_for_dept = {
            "rocks": rocks_by_dept_slack.get(dept_id, {}).get("rocks", []),
            "projects": rocks_by_dept_slack.get(dept_id, {}).get("projects", []),
        }
        any_rocks = any(
            (b.get(dept_id, {}).get("rocks") or b.get(dept_id, {}).get("projects"))
            for b in (rocks_by_dept_slack, rocks_by_dept_doc, rocks_by_dept_deck)
        )
        # Skip depts that are fully dark: no row visible on ANY surface and no
        # rocks anywhere. (This is how founders — seeded all-False — stays off
        # every surface exactly as today, while flipping any founders toggle ON
        # later makes the dept appear with no code change.)
        any_row_lit = any(row.get(s) for row in routing_rows for s in _SURFACES)
        if not (any_row_lit and entries) and not any_rocks:
            continue
        # Phase B+ — founders pre-read consumes the canonical MetricPayload
        # pipeline (closes the dual-pipeline loophole flagged by Phase 0
        # reviewers). Other depts continue on render_one_row until Phase C+E
        # migrates them. Today this branch is forward-looking infrastructure:
        # founders' routing rows seed all-False on every surface, so the
        # all-dark skip rule above excludes founders in current runs — the
        # founders pre-read is a Phase 3 placeholder in recess_os_daily.sh.
        # When Phase 3 lands, this is the only blessed code path; Test #7
        # enforces structurally.
        if dept_id == "founders":
            rows = _build_founders_rendered_rows(company_metrics)
        else:
            rows = [render_one_row(e, dept_id, company_metrics, today) for e in entries]
        rendered_per_dept[dept_id] = {
            "scorecard_rows": rows,
            # NOTE: write-only in production since P2.3 — surface writers take
            # per-surface rock buckets as parameters; this mirrors the SLACK
            # bucket for debugging/audit only. Do not consume for deck/doc.
            "rocks_section": rocks_for_dept,
            "slide_idx": dept_to_slide.get(dept_id),
        }
        # Build a parallel "scorecard_rows" payload from rocks+projects for
        # the rocks deck writer. The deck writer consumes any payload with a
        # `scorecard_rows` list + `slide_idx`, so we reuse the same shape.
        # DECK bucket here — rock visibility is per-surface (P2.3).
        deck_rocks_for_dept = rocks_by_dept_deck.get(dept_id, {})
        rock_rows = [
            render_rock_or_project_row(item, dept_id)
            for item in (deck_rocks_for_dept.get("rocks") or [])
        ]
        project_rows = [
            render_rock_or_project_row(item, dept_id)
            for item in (deck_rocks_for_dept.get("projects") or [])
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
                surface="deck",
                routing=routing,
                registry=registry,
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
            # surface=None: rock rows are not metrics — their deck visibility
            # was applied upstream via rock_visible (deck bucket). The writer
            # must not re-filter them against the metric registry.
            apply_via_slides_api(
                rendered_per_dept=rendered_rocks_per_dept,
                surface=None,
                routing=routing,
                registry=registry,
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
                rocks_by_dept=rocks_by_dept_slack,
                channel_id=slack_channel,
                run_date=today,
                routing=routing,
                registry=registry,
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
                rocks_by_dept=rocks_by_dept_doc,
                doc_id=leadership_doc_id,
                docs_service=docs_service,
                routing=routing,
                registry=registry,
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
