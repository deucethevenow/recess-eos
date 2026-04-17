"""Asana client wrapper for Recess OS sync operations."""
from __future__ import annotations

import os
from typing import Any

import asana


class AsanaAuthError(Exception):
    """Raised when Asana token is missing or invalid."""


class RecessAsanaClient:
    """Wrapper around the official asana SDK for Recess OS sync."""

    def __init__(self, workspace_gid: str):
        token = os.environ.get("ASANA_ACCESS_TOKEN")
        if not token:
            raise AsanaAuthError(
                "ASANA_ACCESS_TOKEN not in environment. Source from "
                "~/Projects/daily-brief-agent/.env first."
            )
        self.workspace_gid = workspace_gid

        config = asana.Configuration()
        config.access_token = token
        self.api_client = asana.ApiClient(config)
        self.portfolios_api = asana.PortfoliosApi(self.api_client)
        self.projects_api = asana.ProjectsApi(self.api_client)
        self.tasks_api = asana.TasksApi(self.api_client)
        self.goals_api = asana.GoalsApi(self.api_client)

    def list_projects_in_portfolio(self, portfolio_gid: str) -> list[dict[str, Any]]:
        """Return all projects in the given portfolio with metadata."""
        opts = {
            "opt_fields": "name,owner.name,owner.email,due_on,created_at,modified_at,custom_fields"
        }
        return list(
            self.portfolios_api.get_items_for_portfolio(portfolio_gid, opts)
        )

    def get_project_tasks(self, project_gid: str) -> list[dict[str, Any]]:
        """Return all tasks in a project with assignee + completion."""
        opts = {
            "opt_fields": "name,assignee.name,assignee.email,completed,completed_at,due_on,is_milestone"
        }
        return list(self.tasks_api.get_tasks_for_project(project_gid, opts))

    def get_goal(self, goal_gid: str) -> dict[str, Any]:
        """Return a single goal with metric data."""
        opts = {
            "opt_fields": "name,owner.name,due_on,metric.current_number_value,metric.target_number_value,metric.unit,time_period.display_name"
        }
        return self.goals_api.get_goal(goal_gid, opts)
