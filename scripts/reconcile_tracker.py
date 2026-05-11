"""Reconcile tracker JSON against live Asana state.

Why this exists (critic IMPORTANT #7): if a human un-completes an Asana task in the
UI, the tracker JSON still says COMPLETED. Silent drift.

This script walks every phase in the tracker, GETs the corresponding Asana task,
and reports any divergence. Read-only by default. Use `--write-back` to overwrite
the tracker from Asana truth.

Drift rules:
  - Asana completed=true                     → tracker should be COMPLETED
  - Asana completed=false                    → tracker should be NOT_STARTED, IN_PROGRESS, or BLOCKED
  - Asana name doesn't start with [KPI SoT]/[ENG] → suspicious; flag

Exit codes:
  0  no drift
  1  drift detected (read-only mode)
  2  Asana / config error

Usage:
    # Detect drift (read-only)
    python scripts/reconcile_tracker.py

    # Write Asana truth back into tracker (only flips status; preserves commit_sha + notes)
    python scripts/reconcile_tracker.py --write-back

Requires:
  ASANA_ACCESS_TOKEN env var (source from ~/Projects/daily-brief-agent/.env)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
import urllib.error
from pathlib import Path

PLAN_DIR = Path(__file__).resolve().parent.parent / "context" / "plans"
TRACKER_PATH = PLAN_DIR / "2026-05-08-monday-kpi-update-sot-tracker.json"

EXPECTED_TASK_NAME_PREFIXES = ("[KPI SoT]", "[ENG]")


def _asana_get(path: str) -> dict:
    token = os.environ.get("ASANA_ACCESS_TOKEN")
    if not token:
        sys.exit("ASANA_ACCESS_TOKEN not set. Source ~/Projects/daily-brief-agent/.env first.")
    url = "https://app.asana.com/api/1.0" + path
    req = urllib.request.Request(
        url,
        method="GET",
        headers={"Authorization": "Bearer " + token},
    )
    try:
        return json.loads(urllib.request.urlopen(req).read())
    except urllib.error.HTTPError as e:
        body_text = e.read().decode()
        sys.exit(f"Asana API error {e.code} on GET {path}: {body_text}")


def _classify_drift(tracker_status: str, asana_completed: bool) -> str | None:
    """Return drift description or None if states agree.
    Treats COMPLETED↔completed=True and {NOT_STARTED, IN_PROGRESS, BLOCKED}↔completed=False as agreement.
    """
    if asana_completed and tracker_status != "COMPLETED":
        return f"Asana completed=true but tracker={tracker_status}"
    if not asana_completed and tracker_status == "COMPLETED":
        return f"Asana completed=false but tracker=COMPLETED"
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--write-back",
        action="store_true",
        help="Overwrite tracker status from Asana truth (preserves commit_sha + notes)",
    )
    args = parser.parse_args()

    tracker = json.loads(TRACKER_PATH.read_text())
    drift_count = 0
    suspicious_count = 0

    for phase_name, phase in tracker["phases"].items():
        gid = phase["asana_gid"]
        response = _asana_get(f"/tasks/{gid}?opt_fields=name,completed")
        task = response["data"]
        name = task.get("name", "")
        completed = task.get("completed", False)

        if not name.startswith(EXPECTED_TASK_NAME_PREFIXES):
            print(
                f"  ⚠ {phase_name}: task name {name!r} doesn't match expected prefixes — SKIPPED"
            )
            suspicious_count += 1
            continue

        drift = _classify_drift(phase["status"], completed)
        if drift is None:
            print(f"  ✓ {phase_name}: in sync ({phase['status']})")
            continue

        drift_count += 1
        print(f"  ⚠ {phase_name}: DRIFT — {drift}")

        if args.write_back:
            new_status = "COMPLETED" if completed else "NOT_STARTED"
            phase["status"] = new_status
            print(f"      → tracker {phase_name} updated to {new_status}")

    print()
    print(f"  {drift_count} phase(s) drifted, {suspicious_count} suspicious")

    # Suspicious takes priority over drift — name-prefix mismatch suggests config drift,
    # not just human un-completion, so we don't auto-write-back over it.
    if suspicious_count > 0:
        return 2
    if drift_count == 0:
        return 0
    if args.write_back:
        TRACKER_PATH.write_text(json.dumps(tracker, indent=2) + "\n")
        print(f"  ✓ Tracker rewritten from Asana truth at {TRACKER_PATH}")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
