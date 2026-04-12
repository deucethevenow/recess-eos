"""Drift reconciliation tests for KPI goal configs.

Hardening A: recess_os.yml is the CANONICAL goal config. kpi_goals.yml is
deprecated and must contain no logic fields. These tests enforce the
single-source-of-truth invariant at the config layer:

1. kpi_goals.yml must not contain any forbidden logic fields.
2. Any active entries in kpi_goals.yml must also exist in recess_os.yml
   with the same asana_goal_id (transitional reconciliation).
3. recess_os.yml goals must all resolve cleanly against the contract layer
   (or be explicitly needs_build).
4. Scorecard metrics in recess_os.yml cannot contain forbidden logic fields.

If this test fails, startup must abort before any output is generated.
"""
from pathlib import Path

import pytest
import yaml

from lib.metric_contract import (
    FORBIDDEN_CONFIG_LOGIC_FIELDS,
    ContractResolutionError,
    resolve_metric_contract,
)


CONFIG_DIR = Path(__file__).parent.parent.parent / "config"
RECESS_OS_YML = CONFIG_DIR / "recess_os.yml"
KPI_GOALS_YML = CONFIG_DIR / "kpi_goals.yml"


def _load_yaml(path: Path) -> dict:
    with open(path) as f:
        return yaml.safe_load(f) or {}


class TestKpiGoalsDeprecation:
    """kpi_goals.yml must not contain transform/threshold logic anymore."""

    def test_kpi_goals_yml_has_no_logic_fields(self):
        """Every entry in kpi_goals.yml must be pointer-only."""
        data = _load_yaml(KPI_GOALS_YML)
        entries = data.get("kpi_goals") or []
        violations = []
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            for forbidden in FORBIDDEN_CONFIG_LOGIC_FIELDS:
                if forbidden in entry:
                    violations.append(
                        f"kpi_goals.yml entry "
                        f"{entry.get('asana_goal_id', '?')} contains forbidden logic "
                        f"field '{forbidden}'. Move it to metric_registry.py and "
                        f"replace with a registry_key reference."
                    )
        assert violations == [], "\n".join(violations)

    def test_kpi_goals_yml_is_empty_or_pointer_only(self):
        """kpi_goals.yml is deprecated — it should be empty or hold only
        pointer-style entries (asana_goal_id + registry_key)."""
        data = _load_yaml(KPI_GOALS_YML)
        entries = data.get("kpi_goals") or []
        allowed_keys = {
            "asana_goal_id",
            "name",
            "owner",
            "rock",
            "registry_key",
            "notes",
            "status",
        }
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            extra = set(entry.keys()) - allowed_keys
            assert not extra, (
                f"kpi_goals.yml entry {entry.get('asana_goal_id', '?')} has "
                f"unexpected keys: {sorted(extra)}. Only pointer fields allowed."
            )


class TestGoalReconciliation:
    """If both files exist, asana_goal_ids must reconcile exactly."""

    def test_every_kpi_goals_entry_appears_in_recess_os_yml(self):
        """Any active goal in kpi_goals.yml MUST have a matching entry in
        recess_os.yml goals section. This is the drift fence."""
        kpi_data = _load_yaml(KPI_GOALS_YML)
        recess_data = _load_yaml(RECESS_OS_YML)

        kpi_goal_ids = {
            e.get("asana_goal_id")
            for e in (kpi_data.get("kpi_goals") or [])
            if isinstance(e, dict) and e.get("asana_goal_id")
        }
        recess_goal_ids = {
            g.get("asana_goal_id")
            for g in (recess_data.get("goals") or [])
            if isinstance(g, dict) and g.get("asana_goal_id")
        }

        orphans = kpi_goal_ids - recess_goal_ids
        assert not orphans, (
            f"Orphan goals in kpi_goals.yml not found in recess_os.yml: "
            f"{sorted(orphans)}. Add them to recess_os.yml `goals` section "
            f"or remove from kpi_goals.yml."
        )

    def test_no_duplicate_goal_ids_across_files(self):
        """Same asana_goal_id in both files must have the same registry_key
        and name. Drift = hard failure."""
        kpi_data = _load_yaml(KPI_GOALS_YML)
        recess_data = _load_yaml(RECESS_OS_YML)

        kpi_by_id = {
            e["asana_goal_id"]: e
            for e in (kpi_data.get("kpi_goals") or [])
            if isinstance(e, dict) and e.get("asana_goal_id")
        }
        recess_by_id = {
            g["asana_goal_id"]: g
            for g in (recess_data.get("goals") or [])
            if isinstance(g, dict) and g.get("asana_goal_id")
        }

        conflicts = []
        for goal_id in set(kpi_by_id) & set(recess_by_id):
            k = kpi_by_id[goal_id]
            r = recess_by_id[goal_id]
            if k.get("registry_key") != r.get("registry_key"):
                conflicts.append(
                    f"{goal_id}: registry_key mismatch "
                    f"(kpi_goals='{k.get('registry_key')}' vs "
                    f"recess_os='{r.get('registry_key')}')"
                )
        assert conflicts == [], "\n".join(conflicts)


class TestRecessOsGoalsResolveCleanly:
    """recess_os.yml `goals` and `scorecard_metrics` must all resolve."""

    def test_all_goals_resolve_or_are_needs_build(self):
        """Every goal in recess_os.yml must resolve against the contract layer.

        For needs_build goals, registry_key is optional. For automated goals,
        resolve_metric_contract() will raise if the registry_key is unknown.
        """
        from lib.config import load_config
        config = load_config(RECESS_OS_YML)
        errors = []

        for goal in config.get("goals", []):
            if not isinstance(goal, dict):
                continue
            # Goals need the same required fields as scorecard metrics
            try:
                resolve_metric_contract(goal)
            except ContractResolutionError as e:
                errors.append(f"goal '{goal.get('name', '?')}': {e}")

        assert errors == [], "\n".join(errors)

    def test_all_scorecard_metrics_resolve(self):
        """Every scorecard metric in recess_os.yml must resolve cleanly."""
        from lib.config import load_config
        config = load_config(RECESS_OS_YML)
        errors = []
        resolved = 0

        for meeting in config.get("meetings", []):
            for m in meeting.get("scorecard_metrics", []):
                if not isinstance(m, dict):
                    continue
                try:
                    resolve_metric_contract(m)
                    resolved += 1
                except ContractResolutionError as e:
                    errors.append(
                        f"{meeting.get('id', '?')}/{m.get('name', '?')}: {e}"
                    )

        assert errors == [], "\n".join(errors)
        assert resolved >= 50, f"Expected ~59 scorecard metrics, got {resolved}"

    def test_goals_section_has_no_forbidden_logic_fields(self):
        """Recess os goals entries cannot contain transform/threshold logic."""
        recess_data = _load_yaml(RECESS_OS_YML)
        violations = []
        for goal in recess_data.get("goals") or []:
            if not isinstance(goal, dict):
                continue
            for forbidden in FORBIDDEN_CONFIG_LOGIC_FIELDS:
                if forbidden in goal:
                    violations.append(
                        f"goal '{goal.get('name', '?')}' has forbidden "
                        f"field '{forbidden}'"
                    )
        assert violations == [], "\n".join(violations)
