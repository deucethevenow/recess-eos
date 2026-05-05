"""Patch 7 contract tests — STATIC_SCORECARD_TARGETS structure + dashboard parity.

Three contract assertions:
  1. Count is 18 (not the 25 the original audit claimed).
  2. "Invoices Overdue" exists; "Overdue Invoices" does NOT (rename).
  3. "Overdue Bill Amount" does NOT exist (no matching dashboard card).
  4. "Days to First Offer" target is 30 (matches dashboard).
"""
import os
import re
from pathlib import Path

import pytest

from lib.static_scorecard_targets import STATIC_SCORECARD_TARGETS


DASHBOARD_REPO = Path(
    os.environ.get(
        "KPI_DASHBOARD_REPO",
        "/Users/deucethevenowworkm1/Projects/company-kpi-dashboard",
    )
)


def test_static_scorecard_targets_has_exactly_18_keys():
    assert len(STATIC_SCORECARD_TARGETS) == 18


def test_invoices_overdue_is_canonical_name_not_overdue_invoices():
    assert "Invoices Overdue" in STATIC_SCORECARD_TARGETS
    assert "Overdue Invoices" not in STATIC_SCORECARD_TARGETS


def test_overdue_bill_amount_removed():
    """Probe 8-7 verified no matching card exists in accounting.py for this key."""
    assert "Overdue Bill Amount" not in STATIC_SCORECARD_TARGETS


def test_days_to_first_offer_target_matches_dashboard():
    """demand_sales.py:1939 hardcodes target=30 for this metric."""
    assert STATIC_SCORECARD_TARGETS["Days to First Offer"] == 30


def test_value_only_metrics_have_explicit_none_target():
    """Pipeline / Bookings / Mktg-Attributed metrics intentionally have no
    target on the dashboard cards. Encoding them as None (rather than
    omitting them) makes the cascade resolve cleanly to 'no target'."""
    for key in (
        "New Business Bookings",
        "Renewal Bookings",
        "L&E Bookings",
        "New Business Pipeline",
        "Renewal Pipeline",
        "Land & Expand Pipeline",
        "Weighted Pipeline",
        "Demand Mktg-Attributed Closed Won",
        "Demand Mktg-Attributed Pipeline",
        "Supply Mktg-Attributed Closed Won",
        "Supply Mktg-Attributed Pipeline",
    ):
        assert key in STATIC_SCORECARD_TARGETS
        assert STATIC_SCORECARD_TARGETS[key] is None


# ----- Cross-source contract: every key has a matching dashboard card ------ #


def test_static_scorecard_targets_match_dashboard_labels():
    """For every key in STATIC_SCORECARD_TARGETS, find a corresponding metric
    on the dashboard. The metric_registry.py is the canonical source of truth
    for which metrics exist; pages/*.py is a secondary lookup for metrics
    rendered via hardcoded card calls. Any drift means the slash command is
    targeting a metric that doesn't exist (or vice versa).

    Search uses a coarse regex over both registry and page files since
    metrics are referenced in many shapes (`"X": {`, `name="X"`,
    `metric_key="X"`, `label="X"`).
    """
    registry_path = DASHBOARD_REPO / "dashboard" / "data" / "metric_registry.py"
    pages_dir = DASHBOARD_REPO / "dashboard" / "pages"
    if not registry_path.exists() and not pages_dir.exists():
        pytest.skip("dashboard registry/pages not found")

    sources_text = ""
    if registry_path.exists():
        sources_text += registry_path.read_text() + "\n"
    if pages_dir.exists():
        sources_text += "\n".join(p.read_text() for p in pages_dir.glob("*.py"))

    missing = []
    for key in STATIC_SCORECARD_TARGETS:
        # Match the key as a string literal anywhere in registry or pages.
        pattern = re.escape(key)
        if not re.search(rf"['\"]{pattern}['\"]", sources_text):
            missing.append(key)

    assert not missing, (
        f"STATIC_SCORECARD_TARGETS keys with no matching dashboard metric: {missing}. "
        "Either add the metric to dashboard/data/metric_registry.py "
        "(or a hardcoded card in pages/*.py) or remove the entry here."
    )
