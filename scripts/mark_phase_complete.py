"""Mark a plan phase complete — flips status in tracker JSON + Asana task.

Updates BOTH:
  1. context/plans/2026-05-08-monday-kpi-update-sot-tracker.json
  2. The corresponding Asana task

Atomic write order (post critic CRITICAL #3):
  1. Validate dependencies (local, cheap)
  2. GET Asana task — verify name prefix + section (CRITICAL #2)
  3. PUT Asana mutation (PUT completed=true OR notes update)
  4. Atomic tracker write via tempfile + os.replace (IMPORTANT #6)

If step 3 fails: tracker untouched, safe to retry.
If step 4 fails: Asana ahead of tracker — caught by scripts/reconcile_tracker.py.

Usage:
    # Mark IN_PROGRESS (no commit yet)
    python scripts/mark_phase_complete.py --phase "Phase 0" --status IN_PROGRESS

    # Mark COMPLETED with commit SHA
    python scripts/mark_phase_complete.py --phase "Phase 0" --commit-sha abc1234

    # Mark BLOCKED with notes
    python scripts/mark_phase_complete.py --phase "Phase B" --status BLOCKED \\
        --note "waiting on Phase 0 yaml fixes"

    # Dry-run (no mutations anywhere — useful for testing)
    python scripts/mark_phase_complete.py --phase "Phase 0" --status COMPLETED --dry-run

    # Tracker-only (skip Asana — useful for offline replay)
    python scripts/mark_phase_complete.py --phase "Phase 0" --commit-sha abc --no-asana

Requires:
  ASANA_ACCESS_TOKEN env var (source from ~/Projects/daily-brief-agent/.env)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

PLAN_DIR = Path(__file__).resolve().parent.parent / "context" / "plans"
TRACKER_PATH = PLAN_DIR / "2026-05-08-monday-kpi-update-sot-tracker.json"

VALID_STATUSES = {"NOT_STARTED", "IN_PROGRESS", "COMPLETED", "BLOCKED"}

# CRITICAL #2: GET-before-PUT validation guards
EXPECTED_TASK_NAME_PREFIXES = ("[KPI SoT]", "[ENG]")
EXPECTED_SECTION_GID = "1213962643949177"


def _asana_request(method: str, path: str, body: dict | None = None) -> dict:
    token = os.environ.get("ASANA_ACCESS_TOKEN")
    if not token:
        sys.exit("ASANA_ACCESS_TOKEN not set. Source ~/Projects/daily-brief-agent/.env first.")
    url = "https://app.asana.com/api/1.0" + path
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Authorization": "Bearer " + token,
            "Content-Type": "application/json",
        },
    )
    try:
        return json.loads(urllib.request.urlopen(req).read())
    except urllib.error.HTTPError as e:
        body_text = e.read().decode()
        sys.exit(f"Asana API error {e.code} on {method} {path}: {body_text}")


def _load_tracker() -> dict:
    if not TRACKER_PATH.exists():
        sys.exit(f"Tracker not found at {TRACKER_PATH}")
    return json.loads(TRACKER_PATH.read_text())


def _save_tracker_atomic(tracker: dict) -> None:
    """IMPORTANT #6: atomic write via tempfile + os.replace.
    Reduces (but doesn't eliminate) tracker.json merge conflicts on multi-session edits.
    Run `git pull --rebase` before invoking the helper if collaborating in parallel.
    """
    fd, tmp_path = tempfile.mkstemp(
        dir=str(TRACKER_PATH.parent), prefix=".tracker.", suffix=".json.tmp"
    )
    try:
        with os.fdopen(fd, "w") as f:
            f.write(json.dumps(tracker, indent=2) + "\n")
        os.replace(tmp_path, TRACKER_PATH)
    except Exception:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise


def _resolve_phase(tracker: dict, phase_arg: str) -> str:
    """CRITICAL #1: phase name normalization with case-insensitive fallback.
    Phases like "Phase C+E" arrive URL-mangled or whitespace-padded; resolve to canonical key.
    """
    candidate = phase_arg.strip()
    if candidate in tracker["phases"]:
        return candidate
    lower = candidate.lower()
    for name in tracker["phases"]:
        if name.lower() == lower:
            return name
    sys.exit(
        f'Phase "{phase_arg}" not in tracker.\n'
        f'Valid phases: ' + ", ".join(tracker["phases"].keys())
    )


def _validate_asana_task(gid: str) -> dict:
    """CRITICAL #2: GET-before-PUT — refuse mutation if task name or section drifted."""
    response = _asana_request(
        "GET", f"/tasks/{gid}?opt_fields=name,memberships.section.gid"
    )
    task = response["data"]
    name = task.get("name", "")
    if not name.startswith(EXPECTED_TASK_NAME_PREFIXES):
        sys.exit(
            f"Refusing to mutate task {gid}: name {name!r} doesn't start with "
            f"any of {EXPECTED_TASK_NAME_PREFIXES}. "
            f"Has the section rotated? Check tracker."
        )
    section_gids = [
        m.get("section", {}).get("gid")
        for m in task.get("memberships", [])
        if m.get("section")
    ]
    if EXPECTED_SECTION_GID not in section_gids:
        sys.exit(
            f"Refusing to mutate task {gid}: memberships {section_gids} don't include "
            f"expected section {EXPECTED_SECTION_GID}. Has the task been moved?"
        )
    return task


def _check_dependencies(tracker: dict, phase_name: str, target_status: str) -> None:
    """IMPORTANT #9: reject COMPLETED transition if any depends_on phase is not COMPLETED.

    Note: deps gate COMPLETED only — IN_PROGRESS / BLOCKED don't check deps. This is
    intentional: a phase may need to start (IN_PROGRESS) to discover that an upstream
    phase needs work; only landing the commit (COMPLETED) requires deps clean.
    """
    if target_status != "COMPLETED":
        return
    deps = tracker["phases"][phase_name].get("depends_on", []) or []
    blocked_by = []
    for dep in deps:
        if dep not in tracker["phases"]:
            sys.exit(f'Phase "{phase_name}" depends_on "{dep}" which is not in tracker.')
        dep_status = tracker["phases"][dep]["status"]
        if dep_status != "COMPLETED":
            blocked_by.append(f"{dep} (status={dep_status})")
    if blocked_by:
        sys.exit(
            f'Cannot mark "{phase_name}" COMPLETED — depends_on not satisfied:\n'
            + "\n".join(f"  - {b}" for b in blocked_by)
        )


def _update_asana_status_in_notes(gid: str, status: str, note: str | None) -> None:
    """IMPORTANT #8: coalesce status flips by overwriting task notes instead of appending stories."""
    timestamp = datetime.now(timezone.utc).isoformat()
    body = f"[helper] last status: {status} at {timestamp}"
    if note:
        body += f"\nnote: {note}"
    _asana_request("PUT", f"/tasks/{gid}", body={"data": {"notes": body}})


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--phase", required=True, help='e.g. "Phase 0", "Phase W.1", "phase c+e"')
    parser.add_argument(
        "--status",
        choices=sorted(VALID_STATUSES),
        help="Override the status. Defaults to COMPLETED if --commit-sha is set, else IN_PROGRESS.",
    )
    parser.add_argument(
        "--commit-sha",
        help="Commit SHA that landed this phase (auto-sets status=COMPLETED)",
    )
    parser.add_argument("--note", help="Append a note to the phase tracker entry")
    parser.add_argument(
        "--no-asana",
        action="store_true",
        help="Update tracker only; skip Asana API (still mutates tracker)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print intended actions without mutating Asana OR tracker",
    )
    args = parser.parse_args()

    if args.commit_sha and not args.status:
        status = "COMPLETED"
    elif args.status:
        status = args.status
    else:
        status = "IN_PROGRESS"

    tracker = _load_tracker()
    phase_name = _resolve_phase(tracker, args.phase)
    phase = tracker["phases"][phase_name]

    _check_dependencies(tracker, phase_name, status)

    if args.dry_run:
        print(f"  [DRY-RUN] Would set {phase_name} → {status}")
        if args.commit_sha:
            print(f"  [DRY-RUN]   commit_sha={args.commit_sha}")
        if not args.no_asana:
            print(f"  [DRY-RUN]   Asana GET {phase['asana_gid']} (validate)")
            if status == "COMPLETED":
                print(f"  [DRY-RUN]   Asana PUT completed=true on {phase['asana_gid']}")
            else:
                print(f"  [DRY-RUN]   Asana PUT notes={status!r} on {phase['asana_gid']}")
        else:
            print("  [DRY-RUN]   Asana skipped (--no-asana)")
        return 0

    if not args.no_asana:
        _validate_asana_task(phase["asana_gid"])
        if status == "COMPLETED":
            _asana_request(
                "PUT",
                f"/tasks/{phase['asana_gid']}",
                body={"data": {"completed": True}},
            )
            print(f"  ✓ Asana task {phase['asana_gid']} marked completed")
        else:
            _update_asana_status_in_notes(phase["asana_gid"], status, args.note)
            print(f"  ✓ Asana task {phase['asana_gid']} notes updated → {status}")

    phase["status"] = status
    if args.commit_sha:
        phase["commit_sha"] = args.commit_sha
    if status == "COMPLETED":
        phase["completed_at"] = datetime.now(timezone.utc).isoformat()
    if args.note:
        phase["notes"] = (phase.get("notes") or "") + " | " + args.note

    _save_tracker_atomic(tracker)
    print(f"  ✓ Tracker updated: {phase_name} → {status}")
    if args.commit_sha:
        print(f"    commit_sha: {args.commit_sha}")
    if args.no_asana:
        print("  (skipped Asana — --no-asana)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
