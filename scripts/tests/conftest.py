"""Shared pytest fixtures for recess_os tests."""
import os
import sys
from pathlib import Path

# Add scripts/ to path so tests can import recess_os modules
sys.path.insert(0, str(Path(__file__).parent.parent))

# v3.8 Patch 1 + Session 3 NIT-2: Add company-kpi-dashboard repo paths so tests
# can import the rendering pipeline reused by /monday-kpi-update from the
# existing cron. Path is overridable via KPI_DASHBOARD_REPO env var so Cloud Run
# (different filesystem layout) and CI (different checkout location) can find it.
DASHBOARD_REPO = Path(
    os.environ.get(
        "KPI_DASHBOARD_REPO",
        "/Users/deucethevenowworkm1/Projects/company-kpi-dashboard",
    )
)
sys.path.insert(0, str(DASHBOARD_REPO))
sys.path.insert(0, str(DASHBOARD_REPO / "dashboard"))
sys.path.insert(0, str(DASHBOARD_REPO / "scripts"))


import pytest


@pytest.fixture
def sample_config_yaml(tmp_path):
    """Returns a path to a temporary recess_os.yml for tests."""
    config = tmp_path / "recess_os.yml"
    config.write_text("""
goals:
  - asana_goal_id: "1213964743621574"
    name: "Test Goal"
    snapshot_table: "kpi_daily_snapshot"
    snapshot_column: "test_metric"
    transform: "raw"
    status: "active"

meetings:
  - id: leadership
    name: "Test Leadership L10"
    facilitator_email: "deuce@recess.is"
    cadence: bi-weekly
    scorecard_metrics:
      - "Net Revenue YTD"

slack_channels:
  recess_goals_kpis: "C0AQP3WH7AB"
  leadership_team: "C05855AJCKF"
""")
    return config


@pytest.fixture
def mock_env(monkeypatch):
    """Set fake env vars so tests don't need real credentials."""
    monkeypatch.setenv("ASANA_ACCESS_TOKEN", "fake-asana-token")
    monkeypatch.setenv("AIRTABLE_API_KEY", "fake-airtable-key")
    monkeypatch.setenv("AIRTABLE_BASE_ID", "fake-base-id")
