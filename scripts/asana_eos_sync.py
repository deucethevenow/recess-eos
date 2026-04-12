#!/usr/bin/env python3
"""
Asana → BigQuery Sync for Recess OS

Syncs Asana Goals, Projects, Tasks, and Sections to BigQuery dataset
`App_Recess_OS`. Designed to run hourly via Cloud Scheduler.

Tables created/updated:
  - eos_rocks: Rock Goals with status, owner, progress
  - eos_rock_tasks: Individual tasks within Rock projects
  - eos_pipeline_items: Scoping Pipeline items with stage and age
  - eos_issues: Issues and Opportunities (filtered from pipeline)
  - eos_todos: Weekly To-Dos (tasks tagged as To-Do or from To-Do project)

Views (created once, read from BQ):
  - v_rock_health: On/At Risk/Off track per Rock
  - v_project_status: Completion %, velocity, blockers per project
  - v_quarterly_summary: Cross-Rock executive summary

Usage:
  python3 scripts/asana_eos_sync.py                  # Full sync
  python3 scripts/asana_eos_sync.py --tables rocks    # Sync only rocks
  python3 scripts/asana_eos_sync.py --dry-run         # Preview without writing
  python3 scripts/asana_eos_sync.py --create-views    # Create/update BQ views

Environment:
  ASANA_ACCESS_TOKEN: Asana personal access token
  GOOGLE_APPLICATION_CREDENTIALS: Path to BQ service account key
  BQ_PROJECT: GCP project ID (default: stitchdata-384118)
  BQ_DATASET: BQ dataset name (default: App_Recess_OS)
  ASANA_WORKSPACE_GID: Asana workspace GID (auto-detected if not set)
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timezone, timedelta
from typing import Any, Optional

import requests

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("asana_eos_sync")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

ASANA_BASE = "https://app.asana.com/api/1.0"
BQ_PROJECT = os.environ.get("BQ_PROJECT", "stitchdata-384118")
BQ_DATASET = os.environ.get("BQ_DATASET", "App_Recess_OS")

# Known Asana project names (updated as projects are created)
# These are used to identify which projects to sync.
# Override with environment variables if needed.
SCOPING_PIPELINE_NAME = os.environ.get("SCOPING_PIPELINE_NAME", "Scoping Pipeline")
ACTIVE_WORK_NAME = os.environ.get("ACTIVE_WORK_NAME", "Active Work")
TODO_PROJECT_NAME = os.environ.get("TODO_PROJECT_NAME", "To-Dos")

# ---------------------------------------------------------------------------
# Asana API Client
# ---------------------------------------------------------------------------


class AsanaClient:
    """Lightweight Asana API client using requests."""

    def __init__(self, token: str):
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        })

    def _get(self, path: str, params: dict | None = None) -> Any:
        """GET request with pagination support."""
        url = f"{ASANA_BASE}{path}"
        all_data = []
        params = params or {}

        while True:
            resp = self.session.get(url, params=params, timeout=30)
            resp.raise_for_status()
            body = resp.json()
            data = body.get("data", [])
            if isinstance(data, list):
                all_data.extend(data)
            else:
                return data  # Single object response

            # Handle pagination
            next_page = body.get("next_page")
            if next_page and next_page.get("offset"):
                params["offset"] = next_page["offset"]
            else:
                break

        return all_data

    def get_workspaces(self) -> list[dict]:
        return self._get("/workspaces")

    def get_goals(self, workspace_gid: str, time_period: str | None = None) -> list[dict]:
        """Get goals for the workspace. time_period is a GID for a time period."""
        params = {"workspace": workspace_gid, "opt_fields": "name,owner,owner.name,status,current_status_update,current_status_update.text,num_subtasks,metric,metric.current_number_value,metric.target_number_value,metric.unit,due_on,start_on,notes"}
        if time_period:
            params["time_periods"] = time_period
        return self._get("/goals", params)

    def get_projects(self, workspace_gid: str, archived: bool = False) -> list[dict]:
        params = {
            "workspace": workspace_gid,
            "archived": str(archived).lower(),
            "opt_fields": "name,owner,owner.name,created_at,modified_at,due_on,start_on,current_status,current_status_update,current_status_update.text,notes,custom_fields",
        }
        return self._get("/projects", params)

    def get_project(self, project_gid: str) -> dict:
        return self._get(f"/projects/{project_gid}", {
            "opt_fields": "name,owner,owner.name,created_at,modified_at,due_on,start_on,notes,custom_fields"
        })

    def get_sections(self, project_gid: str) -> list[dict]:
        return self._get(f"/projects/{project_gid}/sections", {
            "opt_fields": "name,created_at"
        })

    def get_tasks(self, project_gid: str) -> list[dict]:
        return self._get(f"/projects/{project_gid}/tasks", {
            "opt_fields": "name,assignee,assignee.name,completed,completed_at,created_at,due_on,due_at,modified_at,notes,memberships,memberships.section,memberships.section.name,tags,tags.name,custom_fields,num_subtasks",
        })

    def get_task(self, task_gid: str) -> dict:
        return self._get(f"/tasks/{task_gid}", {
            "opt_fields": "name,assignee,assignee.name,completed,completed_at,created_at,due_on,due_at,modified_at,notes,tags,tags.name,custom_fields",
        })


# ---------------------------------------------------------------------------
# BigQuery Writer
# ---------------------------------------------------------------------------


class BigQueryWriter:
    """Thin adapter over RecessOSBQClient for the asana sync.

    Hardening D: direct google.cloud.bigquery.Client instantiation is banned
    outside lib/bq_client.py. This class now routes ALL writes through the
    canonical RecessOSBQClient to preserve the Truth Model (WRITE_TRUNCATE
    for snapshots, MERGE WHEN NOT MATCHED THEN INSERT for events).
    """

    def __init__(self, project: str, dataset: str, dry_run: bool = False):
        self.project = project
        self.dataset = dataset
        self.dry_run = dry_run
        self._canonical: Optional["Any"] = None  # lazy-init; see canonical property

    @property
    def canonical(self):
        """Return the canonical RecessOSBQClient, lazy-initialized on first use.

        Lazy init keeps dry-run paths cheap and avoids credential errors when
        running --dry-run without GOOGLE_APPLICATION_CREDENTIALS set.
        """
        if self._canonical is None:
            from lib.bq_client import RecessOSBQClient
            self._canonical = RecessOSBQClient(project_id=self.project, dataset=self.dataset)
        return self._canonical

    def _table_ref(self, table_name: str) -> str:
        return f"{self.project}.{self.dataset}.{table_name}"

    def write_rows(self, table_name: str, rows: list[dict], schema: list[dict]):
        """Write rows to a BQ snapshot table via the canonical client.

        Snapshot semantics (WRITE_TRUNCATE) match the asana_eos_sync contract:
        every run produces a fresh view of Asana state, old rows are replaced
        atomically.
        """
        if self.dry_run:
            log.info(f"[DRY RUN] Would write {len(rows)} rows to {table_name}")
            if rows:
                log.info(f"  Sample: {json.dumps(rows[0], default=str)[:200]}")
            return

        n = self.canonical.load_snapshot(table_name, rows, schema=schema)
        log.info(f"Wrote {n} rows to {self._table_ref(table_name)}")

    def create_view(self, view_name: str, sql: str):
        """Create or replace a BQ view via the canonical client."""
        if self.dry_run:
            log.info(f"[DRY RUN] Would create view {view_name}")
            return

        self.canonical.create_or_replace_view(view_name, sql)
        log.info(f"Created view {self._table_ref(view_name)}")


# ---------------------------------------------------------------------------
# Sync Logic
# ---------------------------------------------------------------------------

# BQ schemas for each table
SCHEMA_ROCKS = [
    {"name": "goal_gid", "field_type": "STRING", "mode": "REQUIRED"},
    {"name": "name", "field_type": "STRING"},
    {"name": "owner_name", "field_type": "STRING"},
    {"name": "status", "field_type": "STRING"},
    {"name": "status_text", "field_type": "STRING"},
    {"name": "progress_pct", "field_type": "FLOAT64"},
    {"name": "start_on", "field_type": "DATE"},
    {"name": "due_on", "field_type": "DATE"},
    {"name": "notes", "field_type": "STRING"},
    {"name": "project_gid", "field_type": "STRING"},
    {"name": "project_name", "field_type": "STRING"},
    {"name": "synced_at", "field_type": "TIMESTAMP"},
]

SCHEMA_ROCK_TASKS = [
    {"name": "task_gid", "field_type": "STRING", "mode": "REQUIRED"},
    {"name": "rock_goal_gid", "field_type": "STRING"},
    {"name": "project_gid", "field_type": "STRING"},
    {"name": "project_name", "field_type": "STRING"},
    {"name": "section_name", "field_type": "STRING"},
    {"name": "name", "field_type": "STRING"},
    {"name": "assignee_name", "field_type": "STRING"},
    {"name": "completed", "field_type": "BOOLEAN"},
    {"name": "completed_at", "field_type": "TIMESTAMP"},
    {"name": "created_at", "field_type": "TIMESTAMP"},
    {"name": "due_on", "field_type": "DATE"},
    {"name": "modified_at", "field_type": "TIMESTAMP"},
    {"name": "is_overdue", "field_type": "BOOLEAN"},
    {"name": "days_overdue", "field_type": "INT64"},
    {"name": "synced_at", "field_type": "TIMESTAMP"},
]

SCHEMA_PIPELINE_ITEMS = [
    {"name": "task_gid", "field_type": "STRING", "mode": "REQUIRED"},
    {"name": "name", "field_type": "STRING"},
    {"name": "section_name", "field_type": "STRING"},
    {"name": "request_type", "field_type": "STRING"},
    {"name": "size", "field_type": "STRING"},
    {"name": "assignee_name", "field_type": "STRING"},
    {"name": "created_at", "field_type": "TIMESTAMP"},
    {"name": "modified_at", "field_type": "TIMESTAMP"},
    {"name": "due_on", "field_type": "DATE"},
    {"name": "completed", "field_type": "BOOLEAN"},
    {"name": "age_days", "field_type": "INT64"},
    {"name": "stage_age_days", "field_type": "INT64"},
    {"name": "synced_at", "field_type": "TIMESTAMP"},
]

SCHEMA_ISSUES = [
    {"name": "task_gid", "field_type": "STRING", "mode": "REQUIRED"},
    {"name": "name", "field_type": "STRING"},
    {"name": "request_type", "field_type": "STRING"},
    {"name": "pain_rating", "field_type": "INT64"},
    {"name": "department", "field_type": "STRING"},
    {"name": "section_name", "field_type": "STRING"},
    {"name": "assignee_name", "field_type": "STRING"},
    {"name": "created_at", "field_type": "TIMESTAMP"},
    {"name": "completed", "field_type": "BOOLEAN"},
    {"name": "notes", "field_type": "STRING"},
    {"name": "synced_at", "field_type": "TIMESTAMP"},
]

SCHEMA_TODOS = [
    {"name": "task_gid", "field_type": "STRING", "mode": "REQUIRED"},
    {"name": "name", "field_type": "STRING"},
    {"name": "assignee_name", "field_type": "STRING"},
    {"name": "completed", "field_type": "BOOLEAN"},
    {"name": "completed_at", "field_type": "TIMESTAMP"},
    {"name": "created_at", "field_type": "TIMESTAMP"},
    {"name": "due_on", "field_type": "DATE"},
    {"name": "source", "field_type": "STRING"},
    {"name": "synced_at", "field_type": "TIMESTAMP"},
]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _extract_custom_field(task: dict, field_name: str) -> str | None:
    """Extract a custom field value from a task by name (case-insensitive)."""
    for cf in task.get("custom_fields") or []:
        if cf.get("name", "").lower() == field_name.lower():
            # Enum field
            if cf.get("enum_value"):
                return cf["enum_value"].get("name")
            # Text field
            if cf.get("text_value"):
                return cf["text_value"]
            # Number field
            if cf.get("number_value") is not None:
                return str(cf["number_value"])
    return None


def _get_section_name(task: dict) -> str:
    """Get the first section name from task memberships."""
    for m in task.get("memberships") or []:
        section = m.get("section")
        if section and section.get("name"):
            # Skip "(no section)" placeholder
            if section["name"] != "(no section)":
                return section["name"]
    return "Unknown"


def sync_rocks(asana: AsanaClient, bq: BigQueryWriter, workspace_gid: str):
    """Sync Rocks (Asana Goals) and their tasks."""
    log.info("Syncing Rocks (Goals)...")

    goals = asana.get_goals(workspace_gid)
    log.info(f"Found {len(goals)} goals")

    # Get all projects to map goals → projects
    projects = asana.get_projects(workspace_gid)
    project_map = {p["name"]: p for p in projects}

    rock_rows = []
    task_rows = []
    now = _now_iso()

    for goal in goals:
        # Try to find the associated project
        project_gid = None
        project_name = None
        for pname, pdata in project_map.items():
            # Match by goal name being contained in project name, or vice versa
            if goal["name"].lower() in pname.lower() or pname.lower() in goal["name"].lower():
                project_gid = pdata["gid"]
                project_name = pname
                break

        # Calculate progress
        metric = goal.get("metric") or {}
        current = metric.get("current_number_value")
        target = metric.get("target_number_value")
        progress_pct = None
        if current is not None and target is not None and target > 0:
            progress_pct = round((current / target) * 100, 1)

        # Status from latest status update
        status_update = goal.get("current_status_update") or {}
        status_text = status_update.get("text", "")

        rock_rows.append({
            "goal_gid": goal["gid"],
            "name": goal.get("name", ""),
            "owner_name": (goal.get("owner") or {}).get("name", ""),
            "status": goal.get("status", ""),
            "status_text": status_text[:1000] if status_text else "",
            "progress_pct": progress_pct,
            "start_on": goal.get("start_on"),
            "due_on": goal.get("due_on"),
            "notes": (goal.get("notes") or "")[:2000],
            "project_gid": project_gid,
            "project_name": project_name,
            "synced_at": now,
        })

        # Sync tasks if project found
        if project_gid:
            tasks = asana.get_tasks(project_gid)
            log.info(f"  Rock '{goal['name']}' → {len(tasks)} tasks in project '{project_name}'")

            for task in tasks:
                due = task.get("due_on")
                is_overdue = False
                days_overdue = 0
                if due and not task.get("completed"):
                    due_date = datetime.strptime(due, "%Y-%m-%d").date()
                    today = datetime.now(timezone.utc).date()
                    if due_date < today:
                        is_overdue = True
                        days_overdue = (today - due_date).days

                task_rows.append({
                    "task_gid": task["gid"],
                    "rock_goal_gid": goal["gid"],
                    "project_gid": project_gid,
                    "project_name": project_name,
                    "section_name": _get_section_name(task),
                    "name": task.get("name", ""),
                    "assignee_name": (task.get("assignee") or {}).get("name", ""),
                    "completed": task.get("completed", False),
                    "completed_at": task.get("completed_at"),
                    "created_at": task.get("created_at"),
                    "due_on": due,
                    "modified_at": task.get("modified_at"),
                    "is_overdue": is_overdue,
                    "days_overdue": days_overdue,
                    "synced_at": now,
                })

    bq.write_rows("eos_rocks", rock_rows, SCHEMA_ROCKS)
    bq.write_rows("eos_rock_tasks", task_rows, SCHEMA_ROCK_TASKS)


def sync_pipeline(asana: AsanaClient, bq: BigQueryWriter, workspace_gid: str):
    """Sync Scoping Pipeline items."""
    log.info("Syncing Scoping Pipeline...")

    projects = asana.get_projects(workspace_gid)
    pipeline_project = None
    for p in projects:
        if SCOPING_PIPELINE_NAME.lower() in p["name"].lower():
            pipeline_project = p
            break

    if not pipeline_project:
        log.warning(f"Scoping Pipeline project '{SCOPING_PIPELINE_NAME}' not found. Skipping.")
        return

    tasks = asana.get_tasks(pipeline_project["gid"])
    log.info(f"Found {len(tasks)} pipeline items")

    now = _now_iso()
    today = datetime.now(timezone.utc).date()
    pipeline_rows = []
    issue_rows = []

    for task in tasks:
        section = _get_section_name(task)
        request_type = _extract_custom_field(task, "Request Type") or _extract_custom_field(task, "Type") or ""
        size = _extract_custom_field(task, "Size") or ""

        # Calculate age
        created = task.get("created_at", "")
        age_days = 0
        if created:
            try:
                created_date = datetime.fromisoformat(created.replace("Z", "+00:00")).date()
                age_days = (today - created_date).days
            except (ValueError, TypeError):
                pass

        # Stage age: use modified_at as proxy for when it entered current stage
        modified = task.get("modified_at", "")
        stage_age_days = 0
        if modified:
            try:
                modified_date = datetime.fromisoformat(modified.replace("Z", "+00:00")).date()
                stage_age_days = (today - modified_date).days
            except (ValueError, TypeError):
                pass

        row = {
            "task_gid": task["gid"],
            "name": task.get("name", ""),
            "section_name": section,
            "request_type": request_type,
            "size": size,
            "assignee_name": (task.get("assignee") or {}).get("name", ""),
            "created_at": created or None,
            "modified_at": modified or None,
            "due_on": task.get("due_on"),
            "completed": task.get("completed", False),
            "age_days": age_days,
            "stage_age_days": stage_age_days,
            "synced_at": now,
        }
        pipeline_rows.append(row)

        # Filter Issues and Opportunities for the issues table
        if request_type.lower() in ("issue", "opportunity"):
            pain = _extract_custom_field(task, "Pain Rating") or _extract_custom_field(task, "Pain")
            dept = _extract_custom_field(task, "Department") or ""

            issue_rows.append({
                "task_gid": task["gid"],
                "name": task.get("name", ""),
                "request_type": request_type,
                "pain_rating": int(pain) if pain and pain.isdigit() else None,
                "department": dept,
                "section_name": section,
                "assignee_name": (task.get("assignee") or {}).get("name", ""),
                "created_at": created or None,
                "completed": task.get("completed", False),
                "notes": (task.get("notes") or "")[:2000],
                "synced_at": now,
            })

    bq.write_rows("eos_pipeline_items", pipeline_rows, SCHEMA_PIPELINE_ITEMS)
    bq.write_rows("eos_issues", issue_rows, SCHEMA_ISSUES)


def sync_todos(asana: AsanaClient, bq: BigQueryWriter, workspace_gid: str):
    """Sync To-Dos from the To-Do project or tagged tasks."""
    log.info("Syncing To-Dos...")

    projects = asana.get_projects(workspace_gid)
    todo_project = None
    for p in projects:
        if TODO_PROJECT_NAME.lower() in p["name"].lower():
            todo_project = p
            break

    if not todo_project:
        log.warning(f"To-Do project '{TODO_PROJECT_NAME}' not found. Skipping.")
        return

    tasks = asana.get_tasks(todo_project["gid"])
    log.info(f"Found {len(tasks)} To-Dos")

    now = _now_iso()
    rows = []

    for task in tasks:
        rows.append({
            "task_gid": task["gid"],
            "name": task.get("name", ""),
            "assignee_name": (task.get("assignee") or {}).get("name", ""),
            "completed": task.get("completed", False),
            "completed_at": task.get("completed_at"),
            "created_at": task.get("created_at"),
            "due_on": task.get("due_on"),
            "source": "L10" if any("l10" in (t.get("name") or "").lower() for t in task.get("tags") or []) else "Direct",
            "synced_at": now,
        })

    bq.write_rows("eos_todos", rows, SCHEMA_TODOS)


def create_views(bq: BigQueryWriter):
    """Create computed views in BigQuery."""
    log.info("Creating views...")
    ds = f"{BQ_PROJECT}.{BQ_DATASET}"

    # v_rock_health: On/At Risk/Off Track per Rock
    bq.create_view("v_rock_health", f"""
        WITH task_stats AS (
            SELECT
                rock_goal_gid,
                project_name,
                COUNT(*) AS total_tasks,
                COUNTIF(completed) AS completed_tasks,
                COUNTIF(is_overdue) AS overdue_tasks,
                COUNTIF(NOT completed AND NOT is_overdue) AS on_track_tasks,
                MAX(days_overdue) AS max_days_overdue
            FROM `{ds}.eos_rock_tasks`
            GROUP BY rock_goal_gid, project_name
        )
        SELECT
            r.goal_gid,
            r.name AS rock_name,
            r.owner_name,
            r.due_on,
            r.progress_pct,
            r.status_text,
            ts.total_tasks,
            ts.completed_tasks,
            ts.overdue_tasks,
            ts.on_track_tasks,
            ROUND(SAFE_DIVIDE(ts.completed_tasks, ts.total_tasks) * 100, 1) AS completion_pct,
            CASE
                WHEN ts.overdue_tasks >= 3 OR ts.max_days_overdue > 7 THEN 'OFF TRACK'
                WHEN ts.overdue_tasks >= 1 OR SAFE_DIVIDE(ts.completed_tasks, ts.total_tasks) < 0.5 THEN 'AT RISK'
                ELSE 'ON TRACK'
            END AS health_status,
            r.synced_at
        FROM `{ds}.eos_rocks` r
        LEFT JOIN task_stats ts ON r.goal_gid = ts.rock_goal_gid
    """)

    # v_project_status: Completion %, velocity, blockers per project
    bq.create_view("v_project_status", f"""
        WITH task_stats AS (
            SELECT
                project_gid,
                project_name,
                section_name,
                COUNT(*) AS total_tasks,
                COUNTIF(completed) AS completed_tasks,
                COUNTIF(is_overdue) AS overdue_tasks,
                COUNTIF(NOT completed AND NOT is_overdue) AS in_progress_tasks,
                -- Velocity: tasks completed in last 7 days
                COUNTIF(completed AND completed_at >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 7 DAY)) AS completed_this_week,
                COUNTIF(completed AND completed_at >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 14 DAY) AND completed_at < TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 7 DAY)) AS completed_last_week,
                COUNTIF(completed AND completed_at >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 28 DAY)) AS completed_last_28d
            FROM `{ds}.eos_rock_tasks`
            GROUP BY project_gid, project_name, section_name
        ),
        project_summary AS (
            SELECT
                project_gid,
                project_name,
                SUM(total_tasks) AS total_tasks,
                SUM(completed_tasks) AS completed_tasks,
                SUM(overdue_tasks) AS overdue_tasks,
                SUM(in_progress_tasks) AS in_progress_tasks,
                SUM(completed_this_week) AS completed_this_week,
                SUM(completed_last_week) AS completed_last_week,
                ROUND(SAFE_DIVIDE(SUM(completed_last_28d), 4), 1) AS avg_tasks_per_week
            FROM task_stats
            GROUP BY project_gid, project_name
        )
        SELECT
            *,
            ROUND(SAFE_DIVIDE(completed_tasks, total_tasks) * 100, 1) AS completion_pct,
            CASE
                WHEN overdue_tasks >= 3 THEN 'AT RISK'
                WHEN overdue_tasks >= 1 THEN 'NEEDS ATTENTION'
                ELSE 'HEALTHY'
            END AS health_status,
            -- Estimated completion date
            CASE
                WHEN avg_tasks_per_week > 0 AND total_tasks > completed_tasks THEN
                    DATE_ADD(CURRENT_DATE(), INTERVAL CAST(CEIL(SAFE_DIVIDE(total_tasks - completed_tasks, avg_tasks_per_week)) AS INT64) WEEK)
                ELSE NULL
            END AS est_completion_date
        FROM project_summary
    """)

    # v_quarterly_summary: Cross-Rock executive summary
    bq.create_view("v_quarterly_summary", f"""
        SELECT
            r.goal_gid,
            r.name AS rock_name,
            r.owner_name,
            r.due_on,
            r.progress_pct,
            rh.completion_pct AS task_completion_pct,
            rh.health_status,
            rh.total_tasks,
            rh.completed_tasks,
            rh.overdue_tasks,
            -- Pipeline items count
            (SELECT COUNT(*) FROM `{ds}.eos_pipeline_items` WHERE NOT completed) AS total_pipeline_items,
            (SELECT COUNT(*) FROM `{ds}.eos_pipeline_items` WHERE section_name = 'Intake' AND NOT completed) AS intake_items,
            (SELECT COUNT(*) FROM `{ds}.eos_pipeline_items` WHERE section_name = 'Ready' AND NOT completed) AS ready_items,
            -- To-Do completion rate
            (SELECT ROUND(SAFE_DIVIDE(COUNTIF(completed), COUNT(*)) * 100, 1) FROM `{ds}.eos_todos`) AS todo_completion_pct,
            r.synced_at
        FROM `{ds}.eos_rocks` r
        LEFT JOIN `{ds}.v_rock_health` rh ON r.goal_gid = rh.goal_gid
        ORDER BY rh.health_status DESC, r.name
    """)

    log.info("All views created.")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Sync Asana → BigQuery for Recess OS")
    parser.add_argument("--tables", nargs="*", choices=["rocks", "pipeline", "todos", "all"],
                        default=["all"], help="Which tables to sync (default: all)")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing to BQ")
    parser.add_argument("--create-views", action="store_true", help="Create/update BQ views")
    args = parser.parse_args()

    # Validate environment
    token = os.environ.get("ASANA_ACCESS_TOKEN")
    if not token:
        log.error("ASANA_ACCESS_TOKEN not set. Get a token from https://app.asana.com/0/developer-console")
        sys.exit(1)

    asana = AsanaClient(token)
    bq = BigQueryWriter(BQ_PROJECT, BQ_DATASET, dry_run=args.dry_run)

    # Get workspace
    workspace_gid = os.environ.get("ASANA_WORKSPACE_GID")
    if not workspace_gid:
        workspaces = asana.get_workspaces()
        if not workspaces:
            log.error("No Asana workspaces found")
            sys.exit(1)
        workspace_gid = workspaces[0]["gid"]
        log.info(f"Using workspace: {workspaces[0]['name']} ({workspace_gid})")

    tables = args.tables
    if "all" in tables:
        tables = ["rocks", "pipeline", "todos"]

    try:
        if "rocks" in tables:
            sync_rocks(asana, bq, workspace_gid)
        if "pipeline" in tables:
            sync_pipeline(asana, bq, workspace_gid)
        if "todos" in tables:
            sync_todos(asana, bq, workspace_gid)
        if args.create_views:
            create_views(bq)

        log.info("Sync complete!")

    except requests.exceptions.HTTPError as e:
        log.error(f"Asana API error: {e}")
        log.error(f"Response: {e.response.text[:500] if e.response else 'No response'}")
        sys.exit(1)
    except Exception as e:
        log.error(f"Sync failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
