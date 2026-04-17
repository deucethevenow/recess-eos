"""Asana project -> BQ row conversion + sync orchestration.

Snapshot table. Uses load_snapshot (WRITE_TRUNCATE) -- full overwrite per sync.
Deletions in Asana propagate by absence on next sync.

custom_fields_json is stored in DUAL-FORMAT:
  {
    "fields_by_name": {"Project Type": "rock", ...},  -- human-readable
    "fields_by_gid":  {"cf_99": "rock", ...}          -- canonical, rename-safe
  }

Downstream consumers (Phase 1.5 view, status commands) MUST prefer fields_by_gid
for lookups. fields_by_name is for debugging/sample output only. If an Asana
field is renamed, fields_by_gid still works; fields_by_name silently breaks.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Optional


def _custom_field_raw_value(cf: dict) -> Any:
    """Extract the value from an Asana custom_field dict regardless of type."""
    # Asana custom fields have different value keys depending on field type:
    # text_value, number_value, enum_value.name, multi_enum_values[*].name, date_value.date
    if "text_value" in cf and cf["text_value"] is not None:
        return cf["text_value"]
    if "number_value" in cf and cf["number_value"] is not None:
        return cf["number_value"]
    if "enum_value" in cf and cf["enum_value"]:
        return cf["enum_value"].get("name")
    if "date_value" in cf and cf["date_value"]:
        return cf["date_value"].get("date")
    if "multi_enum_values" in cf and cf["multi_enum_values"]:
        return [v.get("name") for v in cf["multi_enum_values"]]
    return None


def _build_custom_fields_json(custom_fields: list) -> str:
    """Build the dual-format custom_fields_json string.

    Returns a JSON string with two top-level keys:
      - fields_by_name: {field_name: value, ...}
      - fields_by_gid:  {field_gid: value, ...}
    """
    by_name = {}
    by_gid = {}
    for cf in custom_fields or []:
        value = _custom_field_raw_value(cf)
        name = cf.get("name")
        gid = cf.get("gid")
        if name:
            by_name[name] = value
        if gid:
            by_gid[gid] = value
    return json.dumps({"fields_by_name": by_name, "fields_by_gid": by_gid})


def _custom_field_value_by_name(custom_fields: list, field_name: str) -> Optional[Any]:
    """Look up a custom field value by name (debugging / legacy path)."""
    for cf in custom_fields or []:
        if cf.get("name") == field_name:
            return _custom_field_raw_value(cf)
    return None


def asana_project_to_bq_row(project: dict) -> dict:
    """Convert one Asana project dict to a BQ row for eos_projects."""
    owner = project.get("owner") or {}
    custom_fields = project.get("custom_fields") or []

    return {
        "asana_project_id": project.get("gid"),
        "name": project.get("name"),
        "owner_email": owner.get("email"),
        "owner_name": owner.get("name"),
        "project_type": _custom_field_value_by_name(custom_fields, "Project Type"),
        "linked_rock_goal_id": _custom_field_value_by_name(custom_fields, "Linked Rock Goal"),
        "linked_rock_id": None,  # derived in Phase 2
        "status": _custom_field_value_by_name(custom_fields, "Status") or "active",
        "quarter": _custom_field_value_by_name(custom_fields, "Quarter"),
        "task_count": project.get("_task_count", 0),
        "completion_percent": project.get("_completion_percent", 0.0),
        "last_activity_at": project.get("modified_at"),
        "custom_fields_json": _build_custom_fields_json(custom_fields),
        "synced_at": datetime.now(timezone.utc).isoformat(),
    }


def sync_projects_to_bq(asana_client, bq_client, portfolio_gid: str) -> int:
    """Sync all projects in the portfolio to App_Recess_OS.eos_projects.

    SNAPSHOT table -- uses load_snapshot (WRITE_TRUNCATE). Full overwrite per sync.
    Pulls task-level completion data for each project to compute completion %.

    Returns:
        Number of rows loaded (may be 0 if portfolio is empty -- still TRUNCATEs).
    """
    projects = asana_client.list_projects_in_portfolio(portfolio_gid)

    # Enrich each project with task + milestone completion data
    for p in projects:
        gid = p.get("gid")
        if gid:
            try:
                tasks = asana_client.get_project_tasks(gid)
                total = len(tasks)
                completed = sum(1 for t in tasks if t.get("completed"))
                milestones = [t for t in tasks if t.get("is_milestone")]
                milestones_done = sum(1 for t in milestones if t.get("completed"))

                p["_task_count"] = total
                # Use milestone completion if milestones exist, else task completion
                if milestones:
                    p["_completion_percent"] = round(milestones_done / len(milestones) * 100, 1)
                elif total > 0:
                    p["_completion_percent"] = round(completed / total * 100, 1)
                else:
                    p["_completion_percent"] = 0.0
            except Exception as e:
                import logging
                logging.getLogger(__name__).warning(
                    "Failed to fetch tasks for project %s: %s", gid, e
                )
                p["_task_count"] = 0
                p["_completion_percent"] = 0.0

    rows = [asana_project_to_bq_row(p) for p in projects]
    n = bq_client.load_snapshot("eos_projects", rows)
    return n
