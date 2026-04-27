#!/usr/bin/env python3
"""Path 1 validation script — All Hands Deck Updater (Task 7).

Proves end-to-end:
  1. render_deck_updates() correctly converts MetricPayload list → SlideReplacement list
  2. Sensitivity filter excludes founders_only metrics from public/leadership runs
  3. Placeholder format matches what's actually inserted in the deck

Test deck: 1qntN3ya_elLPJtWN4cipxO-bZZfgrZS4Zhsdeax_DNE
  Slide 2 Sales — 3 placeholders (public)
  Slide 3 Demand AM — 2 placeholders (public)
  Slide 4 Founders Only — 2 placeholders (founders_only, MUST be filtered out)

This script does NOT call the Slides API. It prints SlideReplacement output that
the operator (or the cron) can then feed to MCP/Slides API for actual replacement.

Usage:
    .venv/bin/python scripts/validate_path1_deck_updater.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "scripts"))

from lib.all_hands_deck import render_deck_updates  # noqa: E402
from lib.metric_payloads import MetricPayload  # noqa: E402


TEST_DECK_ID = "1qntN3ya_elLPJtWN4cipxO-bZZfgrZS4Zhsdeax_DNE"
SNAPSHOT_TIMESTAMP = "2026-04-26T18:00:00Z"


def _payload(
    *,
    dept_id: str,
    registry_key: str,
    display_value: str,
    target: float | None = None,
    sensitivity: str = "public",
    format_spec: str = "currency",
    availability_state: str = "live",
) -> MetricPayload:
    """Minimal MetricPayload constructor for testing."""
    return MetricPayload(
        metric_name=registry_key,
        config_key=registry_key.lower().replace(" ", "_"),
        registry_key=registry_key,
        snapshot_column=registry_key.lower(),
        raw_value=None,
        transformed_value=None,
        target=target,
        display_value=display_value,
        metric_unit="USD" if format_spec == "currency" else "",
        format_spec=format_spec,
        transform="none",
        snapshot_timestamp=SNAPSHOT_TIMESTAMP,
        sensitivity=sensitivity,
        availability_state=availability_state,
        dept_id=dept_id,
        notes=None,
    )


def build_test_payloads() -> dict[str, list[MetricPayload]]:
    """Build payloads matching the test deck's 7 placeholders.

    Sales (3, all public)        — should appear in deck
    Demand AM (2, public)        — should appear in deck
    Founders (2, founders_only)  — MUST be filtered out by render_deck_updates
    """
    return {
        "sales": [
            _payload(dept_id="sales", registry_key="Bookings Goal Attainment",
                     display_value="$2.59M", target=10_770_000.0, format_spec="currency"),
            _payload(dept_id="sales", registry_key="Demand NRR",
                     display_value="13%", target=0.50, format_spec="percent"),
            _payload(dept_id="sales", registry_key="Pipeline Coverage",
                     display_value="0.88x", target=2.5, format_spec="multiplier"),
        ],
        "demand_am": [
            _payload(dept_id="demand_am", registry_key="NPS Score",
                     display_value="79.3", target=75.0, format_spec="number"),
            _payload(dept_id="demand_am", registry_key="Days to Fulfill",
                     display_value="11 days", target=30.0, format_spec="days"),
        ],
        "founders": [
            _payload(dept_id="founders", registry_key="Bank Cash Available",
                     display_value="$2.4M", sensitivity="founders_only", format_spec="currency"),
            _payload(dept_id="founders", registry_key="Conservative Runway",
                     display_value="14 months", sensitivity="founders_only", format_spec="number"),
        ],
    }


def main() -> int:
    payloads = build_test_payloads()

    print("=" * 72)
    print("PATH 1 VALIDATION — All Hands Deck Updater")
    print("=" * 72)
    print()
    print(f"Test deck:    {TEST_DECK_ID}")
    print(f"  Link:       https://docs.google.com/presentation/d/{TEST_DECK_ID}")
    print(f"Snapshot ts:  {SNAPSHOT_TIMESTAMP}")
    print(f"Input depts:  {list(payloads.keys())}")
    print(f"Input count:  {sum(len(v) for v in payloads.values())} payloads "
          f"({sum(1 for v in payloads.values() for p in v if p.sensitivity == 'founders_only')} "
          f"founders_only)")
    print()

    replacements, results = render_deck_updates(payloads, SNAPSHOT_TIMESTAMP)

    print(f"Replacements rendered: {len(replacements)}")
    print(f"Consumer results:      {len(results)}")
    print()
    print("Render output (this is what gets piped to replaceAllTextInSlides):")
    print("-" * 72)
    for r in replacements:
        print(f"  {r.placeholder} → {r.replacement!r}")
    print()
    print("Skipped (sensitivity filtered):")
    print("-" * 72)
    skipped = [r for r in results if r.action == "skipped"]
    for r in skipped:
        print(f"  [{r.dept_id}] {r.registry_key} — {r.error_message}")
    print()

    # ── Assertions ────────────────────────────────────────────────────────
    print("ASSERTIONS:")
    print("-" * 72)

    public_placeholders = {r.placeholder for r in replacements}
    expected_public = {
        "{{sales_bookings_goal_attainment}}",
        "{{sales_demand_nrr}}",
        "{{sales_pipeline_coverage}}",
        "{{demand_am_nps_score}}",
        "{{demand_am_days_to_fulfill}}",
    }
    expected_filtered = {
        "{{founders_bank_cash_available}}",
        "{{founders_conservative_runway}}",
    }

    failed = []

    # 1. All public placeholders rendered
    missing = expected_public - public_placeholders
    if missing:
        failed.append(f"FAIL: missing public placeholders: {missing}")
    else:
        print(f"  PASS: all {len(expected_public)} public placeholders rendered")

    # 2. NO founders placeholders in replacements
    leaked = expected_filtered & public_placeholders
    if leaked:
        failed.append(f"FAIL: founders_only placeholders leaked: {leaked}")
    else:
        print(f"  PASS: 0/{len(expected_filtered)} founders_only placeholders leaked")

    # 3. Skipped count matches founders_only count
    if len(skipped) != len(expected_filtered):
        failed.append(f"FAIL: expected {len(expected_filtered)} skipped, got {len(skipped)}")
    else:
        print(f"  PASS: {len(skipped)} metrics correctly skipped (sensitivity)")

    # 4. Each replacement has a non-empty value
    empty = [r for r in replacements if not r.replacement.strip()]
    if empty:
        failed.append(f"FAIL: {len(empty)} replacements with empty values: "
                      f"{[r.placeholder for r in empty]}")
    else:
        print(f"  PASS: all {len(replacements)} replacements have non-empty values")

    # 5. Targets included in display where present
    bookings = next((r for r in replacements if "bookings" in r.placeholder), None)
    if bookings and "/" not in bookings.replacement:
        failed.append(f"FAIL: target not appended to {bookings.placeholder}: "
                      f"{bookings.replacement!r}")
    else:
        print("  PASS: targets correctly appended to display value")

    print()
    print("=" * 72)
    if failed:
        for f in failed:
            print(f)
        print()
        print(f"VALIDATION FAILED: {len(failed)} assertion(s)")
        return 1

    print("VALIDATION PASSED")
    print("=" * 72)
    print()
    print("Next step: feed these replacements to mcp__google-drive__replaceAllTextInSlides")
    print("           to actually update the test deck, then re-fetch + verify.")
    print()

    # ── JSON output for downstream MCP calls ──────────────────────────────
    out_path = _REPO_ROOT / "context" / "evidence" / "2026-04-26-path1-deck-validation"
    out_path.mkdir(parents=True, exist_ok=True)
    json_file = out_path / "replacements.json"
    json_file.write_text(json.dumps([
        {"placeholder": r.placeholder, "replacement": r.replacement,
         "dept_id": r.dept_id, "registry_key": r.registry_key,
         "metric_name": r.metric_name}
        for r in replacements
    ], indent=2))
    print(f"Wrote {len(replacements)} replacements to {json_file}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
