"""STATIC_SCORECARD_TARGETS — slash-command-owned target map.

Per v3.8 Patch 7 (closes B18, audit at
context/evidence/2026-04-23-batch6-cloud-run-migration/21-target-source-audit.md).

This map covers the 18 metrics where the dashboard pages hardcode the target in
render code rather than via the registry's `target_key`. The slash command's
4-step target cascade falls through to this map when neither registry-side path
returns a value.

Phase 1.5 cleanup: migrate non-None entries to the registry's `scorecard_target`
field so this dict can be deleted. Tracked separately.

v3.8 corrections vs v3.7:
  - count is 18 (audit said 25, audit was wrong; counted by hand: 18 entries here).
  - "Overdue Invoices" renamed → "Invoices Overdue" (matches accounting.py:81).
  - "Overdue Bill Amount" removed (no matching card on accounting.py — verified
    2026-05-05 against grep of dashboard/pages/accounting.py).
  - "Days to First Offer" target=30 verified against demand_sales.py:1939.
"""
from typing import Dict, Optional

STATIC_SCORECARD_TARGETS: Dict[str, Optional[float]] = {
    # Targeted metrics (numeric target; dashboard page hardcodes the value)
    "Invoice Collection Rate": 0.95,
    "Avg Days to Collection": 30,
    "Bills Overdue": 0,
    "Invoices Overdue": 0,
    "Overdue Amount": 0,
    "Days to First Offer": 30,
    # Value-only metrics (no target — dashboard cards intentionally omit one)
    "Paid Within 7 Days": None,
    "New Business Bookings": None,
    "Renewal Bookings": None,
    "L&E Bookings": None,
    "New Business Pipeline": None,
    "Renewal Pipeline": None,
    "Land & Expand Pipeline": None,
    "Weighted Pipeline": None,
    "Demand Mktg-Attributed Closed Won": None,
    "Demand Mktg-Attributed Pipeline": None,
    "Supply Mktg-Attributed Closed Won": None,
    "Supply Mktg-Attributed Pipeline": None,
}

# O4 fix from review: count contract is enforced by
# test_static_scorecard_targets_has_exactly_18_keys (in test_static_scorecard_targets.py),
# NOT by a module-level assert that would crash production at import time.
