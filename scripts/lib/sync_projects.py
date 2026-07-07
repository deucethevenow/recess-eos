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
import re
from datetime import datetime, timezone
from typing import Any, Optional

# P3 fallback stamps (Metric Routing plan Phase 3): the Q3 2026 portfolio's
# "Project Type"/"Quarter" Asana custom fields are EMPTY, which left NULLs in
# BQ and broke rock classification downstream (dashboard name-sniff expected
# the Q2 "Rock N:" prefix; Q3 names are "Q3 Rock: ..." / "(Marketing Rock —
# Q3 2026)"). When the fields are empty we stamp derived values at sync time
# so downstream consumers can TRUST project_type/quarter. Regexes assigned to
# module vars (no backslashes inside f-string braces — py3.9 house rule).
_PORTFOLIO_QUARTER_RE = re.compile(r"^Q([1-4]) (\d{4}) Rocks \+ Projects$")
_ROCK_WORD_RE = re.compile(r"\brock\b", re.IGNORECASE)


def derive_quarter_from_portfolio_name(portfolio_name: Optional[str]) -> Optional[str]:
    """'Q3 2026 Rocks + Projects' -> '2026-Q3'; None when the name doesn't match."""
    if not portfolio_name:
        return None
    m = _PORTFOLIO_QUARTER_RE.match(portfolio_name.strip())
    if not m:
        return None
    return f"{m.group(2)}-Q{m.group(1)}"


def derive_project_type_from_name(name: Optional[str]) -> str:
    """Whole-word 'rock' (case-insensitive) anywhere in the name -> 'rock',
    else 'project'. Whole-word so 'RockStar'/'Rockets' never match."""
    if name and _ROCK_WORD_RE.search(name):
        return "rock"
    return "project"


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


def asana_project_to_bq_row(project: dict, quarter_fallback: Optional[str] = None) -> dict:
    """Convert one Asana project dict to a BQ row for eos_projects.

    P3 FALLBACK stamps (only when the Asana custom field is empty):
      project_type <- whole-word 'rock' in the project name, else 'project'
                      (ALWAYS non-null from here on — consumers trust it)
      quarter      <- `quarter_fallback` (parsed from the portfolio name),
                      honest-NULL when no fallback is derivable
    Populated Asana fields always win, untouched.
    """
    owner = project.get("owner") or {}
    custom_fields = project.get("custom_fields") or []
    name = project.get("name")

    project_type = _custom_field_value_by_name(custom_fields, "Project Type")
    if not project_type:
        project_type = derive_project_type_from_name(name)
    quarter = _custom_field_value_by_name(custom_fields, "Quarter")
    if not quarter:
        quarter = quarter_fallback

    return {
        "asana_project_id": project.get("gid"),
        "name": name,
        "owner_email": owner.get("email"),
        "owner_name": owner.get("name"),
        "project_type": project_type,
        "linked_rock_goal_id": _custom_field_value_by_name(custom_fields, "Linked Rock Goal"),
        "linked_rock_id": None,  # derived in Phase 2
        "status": _custom_field_value_by_name(custom_fields, "Status") or "active",
        "quarter": quarter,
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

    # P3: derive the quarter fallback ONCE from the portfolio name ("Q3 2026
    # Rocks + Projects" -> "2026-Q3"). Because load_snapshot is WRITE_TRUNCATE,
    # the stamps reach ALL rows on every sync — no backfill step needed.
    portfolio_name = None
    if hasattr(asana_client, "get_portfolio_name"):
        portfolio_name = asana_client.get_portfolio_name(portfolio_gid)
    quarter_fallback = derive_quarter_from_portfolio_name(portfolio_name)

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

    rows = [asana_project_to_bq_row(p, quarter_fallback=quarter_fallback) for p in projects]
    n = bq_client.load_snapshot("eos_projects", rows)
    return n
