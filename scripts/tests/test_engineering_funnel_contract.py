"""Patch 9 contract test — engineering funnel SQL ↔ registry stage labels.

Stage labels in the registry's `field: "stage:X"` entries are matched
case-sensitively against string literals in view5-discovery-funnel.sql. A SQL
refactor (rename, capitalization change, trailing space) would silently
return None and render as '—' in the dashboard — no error, no log.

This contract test fails LOUD at CI time so SQL drift can't ship silently.
"""
import os
import re
from pathlib import Path

import pytest

DASHBOARD_REPO = Path(
    os.environ.get(
        "KPI_DASHBOARD_REPO",
        "/Users/deucethevenowworkm1/Projects/company-kpi-dashboard",
    )
)
VIEW5_SQL = DASHBOARD_REPO / "dashboard" / "data" / "engineering_queries" / "view5-discovery-funnel.sql"


def _registry_stage_labels():
    """Collect every `field: stage:X` entry from the metric registry."""
    from dashboard.data.metric_registry import METRIC_REGISTRY  # type: ignore

    labels = set()
    for key, entry in METRIC_REGISTRY.items():
        field = entry.get("field") or ""
        if field.startswith("stage:"):
            labels.add(field.split(":", 1)[1])
    return labels


def _extract_sql_string_literals(sql_text):
    """Pull string literals from the SQL — used as stage labels in CASE/WHEN."""
    return set(re.findall(r"'([A-Z][A-Za-z _-]+)'", sql_text))


def test_stage_labels_match_engineering_live_funnel_sql():
    if not VIEW5_SQL.exists():
        pytest.skip(f"funnel SQL not found at {VIEW5_SQL} — skipping contract check")

    sql = VIEW5_SQL.read_text()
    sql_labels = _extract_sql_string_literals(sql)
    registry_labels = _registry_stage_labels()

    if not registry_labels:
        pytest.skip(
            "No registry entries with field='stage:X' found — funnel wiring "
            "still pending. Contract is vacuously satisfied; will activate "
            "once Engineering live wiring lands (Phase 2)."
        )

    missing = registry_labels - sql_labels
    assert not missing, (
        f"Registry references stage labels not present in funnel SQL: {missing}. "
        f"SQL labels found: {sorted(sql_labels)}. Either fix the registry "
        f"stage strings or the SQL string literals — they MUST match exactly "
        f"(case + spaces)."
    )
