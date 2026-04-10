"""Config loader for recess_os.yml."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

import yaml


class ConfigError(Exception):
    """Raised when config loading or validation fails."""


def load_config(path: Path) -> dict[str, Any]:
    """Load and parse recess_os.yml.

    Args:
        path: Absolute path to the config file.

    Returns:
        Parsed config dict.

    Raises:
        ConfigError: If file missing or YAML is invalid.
    """
    path = Path(path)
    if not path.exists():
        raise ConfigError(f"Config file not found: {path}")

    try:
        with open(path) as f:
            return yaml.safe_load(f) or {}
    except yaml.YAMLError as e:
        raise ConfigError(f"Failed to parse YAML at {path}: {e}") from e


def get_active_goals(config: dict[str, Any]) -> list[dict[str, Any]]:
    """Return only goals with status='active' from the config."""
    return [g for g in config.get("goals", []) if g.get("status") == "active"]


def get_meeting(config: dict[str, Any], meeting_id: str) -> Optional[dict[str, Any]]:
    """Return the meeting config matching the given id, or None."""
    for meeting in config.get("meetings", []):
        if meeting.get("id") == meeting_id:
            return meeting
    return None
