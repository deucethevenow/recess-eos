"""Single source of truth for the company-kpi-dashboard repo location.

Phase H.2 extracted this from scorecard_renderer.py / conftest.py / 4 test
files to eliminate 6-way duplication. Importing this module is enough to put
the dashboard repo paths on sys.path; downstream callers can then do:

    from post_monday_pulse import _render_metric_line
    from data.metric_registry import METRIC_REGISTRY

Override via KPI_DASHBOARD_REPO env var (Cloud Run / CI / dev mounts).
"""
import os
import sys
from pathlib import Path

DASHBOARD_REPO = Path(
    os.environ.get(
        "KPI_DASHBOARD_REPO",
        "/Users/deucethevenowworkm1/Projects/company-kpi-dashboard",
    )
)


def _ensure_on_path() -> None:
    """Idempotent: prepend the 3 dashboard import roots to sys.path.

    Raises ImportError with an actionable message if DASHBOARD_REPO doesn't
    exist on disk. Catches the Cloud Run / fresh-checkout case where the
    default `/Users/deucethevenowworkm1/...` path is invalid AND
    KPI_DASHBOARD_REPO wasn't set — without this check, the downstream
    `from post_monday_pulse import ...` would raise a generic
    ModuleNotFoundError with no hint about the actual root cause.
    """
    if not DASHBOARD_REPO.exists():
        raise ImportError(
            f"company-kpi-dashboard repo not found at {DASHBOARD_REPO}. "
            f"Either clone the repo to that path, OR set the KPI_DASHBOARD_REPO "
            f"env var to the actual location (Cloud Run / CI / other dev mounts)."
        )
    for p in (DASHBOARD_REPO, DASHBOARD_REPO / "dashboard", DASHBOARD_REPO / "scripts"):
        ps = str(p)
        if ps not in sys.path:
            sys.path.insert(0, ps)


_ensure_on_path()
