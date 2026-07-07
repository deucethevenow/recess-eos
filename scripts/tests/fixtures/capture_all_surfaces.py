"""Metric Routing P2 — all-surface golden capture with FROZEN inputs.

Extends the Phase H capture_golden.py precedent to every Monday-update surface,
with one crucial addition: live inputs are frozen to a JSON file once, then every
capture run replays those frozen inputs. Pre- vs post-migration diffs are therefore
pure render-pipeline diffs — no BQ/HubSpot/Asana drift can fake a regression.

Surfaces captured per run (written to --out DIR):
  eos_deck_requests.json        deck scorecard batchUpdate bodies (fake Slides svc)
  eos_rocks_deck_requests.json  rocks/projects slides batchUpdate bodies
  eos_slack_blocks.json         Slack Block Kit via injected slack_post_fn
  eos_doc_requests.json         leadership-doc batchUpdate bodies (fake Docs svc)
  pulse_blocks.json             dashboard post_monday_pulse Block Kit (--show-json)
  pulse_stdout.txt              dashboard pulse full preview stdout
  failure_alerts.json           every emit_failure_alert call (must be [] on green)
  meta.json                     run date, HEAD SHAs, frozen-inputs path

Usage (from the eos worktree, py .venv):
  # 1. Freeze live inputs ONCE (needs BQ creds + daily-brief-agent/.env for Asana):
  scripts/.venv/bin/python scripts/tests/fixtures/capture_all_surfaces.py \
      --freeze scripts/tests/fixtures/golden_p2/frozen_inputs.json
  # 2. Capture golden (pre-migration) and later the post-migration run:
  ... capture_all_surfaces.py --inputs .../frozen_inputs.json --out .../golden_p2/pre
  ... capture_all_surfaces.py --inputs .../frozen_inputs.json --out .../golden_p2/post
  # 3. diff -r pre post

Side effects: NONE on capture (all writers faked; failure alerts recorded, not
posted). Freeze mode reads BQ/Firestore/Asana read-only.
"""
from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import sys
from datetime import date as _date
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import MagicMock

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

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


# --------------------------------------------------------------------------- #
# Freeze — capture every live input the two render pipelines consume          #
# --------------------------------------------------------------------------- #


def do_freeze(out_path: Path) -> int:
    import data.bigquery_client as bqc
    import data.targets_manager as tm
    from dashboard.data import data_layer as dl

    frozen: Dict[str, Any] = {}
    frozen["company_metrics"] = dl.get_company_metrics()
    frozen["rock_data"] = dl.get_rock_project_progress() or {"available": False}
    # Pulse-side data_layer reads (review P2 Important #2 — these bind via the
    # `data.` namespace inside post_monday_pulse and MUST be frozen too):
    frozen["revenue_actuals"] = dl.get_revenue_actuals()
    frozen["supply_contact_attempts"] = dl.get_supply_contact_attempts_data()
    frozen["pipeline_by_owner"] = {
        "quarter": bqc.get_pipeline_coverage_by_owner(period="quarter"),
        "year": bqc.get_pipeline_coverage_by_owner(period="year"),
    }
    today = _date.today()
    quarter = (today.month - 1) // 3 + 1
    frozen["team_quota"] = {
        "year": today.year,
        "quarter": quarter,
        "value": tm.get_team_quota(year=today.year, quarter=quarter),
    }

    # Pulse module caches: import UNPATCHED (module-level COMPANY_METRICS fires
    # a live snapshot read — fine here), then harvest Leo projects + Asana goals.
    import post_monday_pulse as pulse  # noqa: E402

    frozen["leo_projects"] = pulse.fetch_leo_projects()
    goals: Dict[str, Any] = {}
    from data.metric_registry import METRIC_REGISTRY  # noqa: E402
    for name, entry in METRIC_REGISTRY.items():
        gid = entry.get("scorecard_asana_goal_id")
        if entry.get("scorecard_status") == "asana_goal" and gid:
            goals[str(gid)] = pulse.fetch_asana_goal(str(gid))
    frozen["asana_goals"] = goals
    frozen["frozen_on"] = today.isoformat()

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(frozen, indent=2, sort_keys=True, default=str))
    print(
        f"[freeze] wrote {out_path} — company_metrics keys={len(frozen['company_metrics'])}, "
        f"rocks={len(frozen['rock_data'].get('rocks') or [])}, "
        f"projects={len(frozen['rock_data'].get('projects') or [])}, "
        f"pipeline owners q/y={len(frozen['pipeline_by_owner']['quarter'])}/"
        f"{len(frozen['pipeline_by_owner']['year'])}, "
        f"team_quota={frozen['team_quota']['value']}, "
        f"leo={len(frozen['leo_projects'])}, asana_goals={len(goals)}"
    )
    return 0


# --------------------------------------------------------------------------- #
# Fakes                                                                       #
# --------------------------------------------------------------------------- #


class _Exec:
    def __init__(self, result):
        self._result = result

    def execute(self):
        return self._result() if callable(self._result) else self._result


class FakeSlidesService:
    """Minimal Slides API double: .presentations().get()/.batchUpdate() chains."""

    def __init__(self, presentation: Dict[str, Any]):
        self.presentation = presentation
        self.batch_updates: List[Dict[str, Any]] = []

    def presentations(self):
        return self

    def get(self, presentationId):  # noqa: N803 — Google API arg style
        return _Exec(self.presentation)

    def batchUpdate(self, presentationId, body):  # noqa: N802, N803
        self.batch_updates.append({"presentationId": presentationId, "body": body})
        return _Exec({})


class FakeDocsService:
    """Minimal Docs API double with an empty sentinel pair in the body."""

    def __init__(self):
        sent = "<<KPI_LEADERSHIP_START>><<KPI_LEADERSHIP_END>>\n"
        self.doc = {
            "body": {
                "content": [
                    {
                        "paragraph": {
                            "elements": [
                                {"startIndex": 1, "textRun": {"content": sent}}
                            ]
                        }
                    }
                ]
            }
        }
        self.batch_updates: List[Dict[str, Any]] = []

    def documents(self):
        return self

    def get(self, documentId, includeTabsContent=None):  # noqa: N803
        return _Exec(self.doc)

    def batchUpdate(self, documentId, body):  # noqa: N802, N803
        self.batch_updates.append({"documentId": documentId, "body": body})
        return _Exec({})


def build_fake_presentation() -> Dict[str, Any]:
    """One scorecard + one rocks slide per mapped dept, each with a 20x5 table.

    20 rows = header + up to 17 data rows + buffer, satisfying preflight's
    header+N+2 headroom for the largest dept (sales, 12 rows).
    """
    from lib.dept_slide_map import DEPT_TITLE_MAP, DEPT_ROCKS_TITLE_MAP

    def slide_for(title: str) -> Dict[str, Any]:
        empty_cell = {"text": {"textElements": []}}
        return {
            "pageElements": [
                {"shape": {"text": {"textElements": [{"textRun": {"content": title}}]}}},
                {
                    "objectId": f"table::{title}",
                    "table": {
                        "columns": 5,
                        "tableRows": [
                            {"tableCells": [dict(empty_cell) for _ in range(5)]}
                            for _ in range(20)
                        ],
                    },
                },
            ]
        }

    slides = []
    for dept, title in DEPT_TITLE_MAP.items():
        slides.append(slide_for(title))
        slides.append(slide_for(DEPT_ROCKS_TITLE_MAP[dept]))
    return {"slides": slides}


# --------------------------------------------------------------------------- #
# Capture                                                                     #
# --------------------------------------------------------------------------- #


def do_capture(inputs_path: Path, out_dir: Path) -> int:
    frozen = json.loads(inputs_path.read_text())
    out_dir.mkdir(parents=True, exist_ok=True)

    alerts: List[Dict[str, Any]] = []

    # ---- Patch order matters: live-input modules FIRST, then pulse/eos ------ #
    import lib.failure_alert as fa

    def _record_alert(**kwargs):
        # exc objects aren't JSON-safe — stringify
        rec = {k: (str(v) if k == "exc" else v) for k, v in kwargs.items()}
        alerts.append(rec)

    fa.emit_failure_alert = _record_alert

    import data.bigquery_client as bqc
    import data.targets_manager as tm
    import data.data_layer as dl_flat
    from dashboard.data import data_layer as dl

    # CRITICAL (review P2 Important #2): `data.data_layer` and
    # `dashboard.data.data_layer` are DISTINCT module instances of the same
    # file (no dashboard/__init__.py). post_monday_pulse binds the flat one;
    # monday_kpi_update binds the namespaced one. Patch BOTH, always.
    for mod in (dl, dl_flat):
        mod.get_company_metrics = lambda: frozen["company_metrics"]
        mod.get_rock_project_progress = lambda: frozen["rock_data"]
        mod.get_revenue_actuals = lambda: frozen["revenue_actuals"]
        mod.get_supply_contact_attempts_data = lambda: frozen["supply_contact_attempts"]
        # Each instance computed COMPANY_METRICS at ITS import (live). Mutate the
        # dict IN PLACE so `from ... import COMPANY_METRICS` bindings see frozen
        # values (same object identity).
        if hasattr(mod, "COMPANY_METRICS") and isinstance(mod.COMPANY_METRICS, dict):
            mod.COMPANY_METRICS.clear()
            mod.COMPANY_METRICS.update(frozen["company_metrics"])
    bqc.get_pipeline_coverage_by_owner = (
        lambda period="quarter", **kw: frozen["pipeline_by_owner"][period]
    )
    tm.get_team_quota = lambda year=None, quarter=None, **kw: frozen["team_quota"]["value"]

    import post_monday_pulse as pulse  # noqa: E402  (binds patched fns)

    pulse._leo_projects_cache = frozen["leo_projects"]
    pulse._asana_goal_cache.update(frozen["asana_goals"])
    pulse._asana_token_cache = "frozen"  # cache hits make the token unused
    if hasattr(pulse, "COMPANY_METRICS") and isinstance(pulse.COMPANY_METRICS, dict):
        pulse.COMPANY_METRICS.clear()
        pulse.COMPANY_METRICS.update(frozen["company_metrics"])
    if hasattr(pulse, "emit_failure_alert"):
        pulse.emit_failure_alert = _record_alert

    # ---- Surface 1: dashboard pulse via its REAL main() (--show-json) ------- #
    old_argv = sys.argv
    sys.argv = ["post_monday_pulse.py", "--show-json"]
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            rc = pulse.main()
    finally:
        sys.argv = old_argv
    stdout_text = buf.getvalue()
    (out_dir / "pulse_stdout.txt").write_text(stdout_text)
    marker = "--- Slack Block Kit JSON ---"
    if marker not in stdout_text or rc != 0:
        print(f"[capture] ERROR: pulse main rc={rc}, marker found={marker in stdout_text}",
              file=sys.stderr)
        return 1
    pulse_json = json.loads(stdout_text.split(marker, 1)[1])
    (out_dir / "pulse_blocks.json").write_text(
        json.dumps(pulse_json, indent=2, sort_keys=True)
    )

    # ---- Surface 2-4: eos monday_kpi_update via REAL main() with fakes ------ #
    import monday_kpi_update as mku  # noqa: E402  (binds patched fns)

    if hasattr(mku, "emit_failure_alert"):
        mku.emit_failure_alert = _record_alert
    import lib.preflight as preflight_mod

    preflight_mod.emit_failure_alert = _record_alert

    fake_pres = build_fake_presentation()
    fake_slides = FakeSlidesService(fake_pres)
    fake_docs = FakeDocsService()
    slack_captured: List[Dict[str, Any]] = []

    def slack_capture_fn(*, channel_id: str, blocks: List[Dict[str, Any]]) -> str:
        slack_captured.append({"channel_id": channel_id, "blocks": blocks})
        return "TS_CAPTURE"

    fake_db = MagicMock()
    fake_doc_ref = fake_db.collection.return_value.document.return_value
    fake_doc_ref.get.return_value.exists = False
    fake_doc_ref.get.return_value.to_dict.return_value = {}

    from lib.deck_writer import build_table_row_count_fetcher

    n_scorecard_updates_before = 0
    with contextlib.redirect_stdout(io.StringIO()) as eos_out:
        mku.main(
            skip_deck=False,
            skip_rocks_deck=False,
            skip_slack=False,
            include_leadership_doc=True,
            leadership_doc_id="FAKE_DOC_ID",
            deck_id="FAKE_DECK_ID",
            fetch_presentation=lambda deck_id: fake_pres,
            fetch_table_row_count=build_table_row_count_fetcher(fake_slides),
            slides_service=fake_slides,
            docs_service=fake_docs,
            slack_post_fn=slack_capture_fn,
            firestore_client=fake_db,
            input_fn=lambda _: "y",
        )
    (out_dir / "eos_stdout.txt").write_text(eos_out.getvalue())

    # apply_via_slides_api runs twice (scorecard then rocks) against the same
    # fake service; split the recorded batches by which table objectIds they hit.
    scorecard_updates, rocks_updates = [], []
    for upd in fake_slides.batch_updates:
        ids = {
            req.get(k, {}).get("objectId")
            for req in upd["body"]["requests"]
            for k in ("insertText", "deleteText")
            if k in req
        }
        if any(i and "Rocks & Projects" in i for i in ids):
            rocks_updates.append(upd)
        else:
            scorecard_updates.append(upd)

    (out_dir / "eos_deck_requests.json").write_text(
        json.dumps(scorecard_updates, indent=2, sort_keys=True)
    )
    (out_dir / "eos_rocks_deck_requests.json").write_text(
        json.dumps(rocks_updates, indent=2, sort_keys=True)
    )
    (out_dir / "eos_slack_blocks.json").write_text(
        json.dumps(slack_captured, indent=2, sort_keys=True)
    )
    (out_dir / "eos_doc_requests.json").write_text(
        json.dumps(fake_docs.batch_updates, indent=2, sort_keys=True)
    )
    (out_dir / "failure_alerts.json").write_text(
        json.dumps(alerts, indent=2, sort_keys=True, default=str)
    )
    (out_dir / "meta.json").write_text(
        json.dumps(
            {
                "run_date": _date.today().isoformat(),
                "inputs": str(inputs_path),
                "frozen_on": frozen.get("frozen_on"),
                "kpi_dashboard_repo": str(DASHBOARD_REPO),
            },
            indent=2,
            sort_keys=True,
        )
    )

    print(
        f"[capture] {out_dir}: pulse_blocks={len(pulse_json.get('blocks', []))} "
        f"deck_batches={len(scorecard_updates)} rocks_batches={len(rocks_updates)} "
        f"slack_msgs={len(slack_captured)} doc_batches={len(fake_docs.batch_updates)} "
        f"alerts={len(alerts)}"
    )
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--freeze", type=Path, help="capture live inputs to this JSON path")
    mode.add_argument("--inputs", type=Path, help="frozen inputs JSON to replay")
    ap.add_argument("--out", type=Path, help="output dir for surface captures (with --inputs)")
    args = ap.parse_args()

    if args.freeze:
        return do_freeze(args.freeze)
    if not args.out:
        ap.error("--inputs requires --out")
    return do_capture(args.inputs, args.out)


if __name__ == "__main__":
    raise SystemExit(main())
