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
        assert resolved >= 50, f"Expected ~63 scorecard metrics, got {resolved}"

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


class TestPhase0Canonicalization:
    """Phase 0 — yaml founders fixes + Renewal canonical rename + Q NR adds.

    Verifies the data corrections for founders sensitivity (Bank Cash and
    Conservative Runway are manual-entry, not automated), the Renewal canonical
    display name, and the new Net Revenue Q (Actual/Forecast) entries on Sales
    and Leadership scorecards. New entries follow the L&E Bookings Pacing
    pattern (registry_key=null, status=needs_build) until Phase W.2 wires the
    live handlers.
    """

    @staticmethod
    def _meetings_by_id(data: dict) -> dict:
        return {
            m.get("id"): m
            for m in data.get("meetings", [])
            if isinstance(m, dict)
        }

    def test_founders_bank_cash_status_is_manual(self):
        data = _load_yaml(RECESS_OS_YML)
        founders = self._meetings_by_id(data).get("founders") or {}
        metrics = {
            m["name"]: m
            for m in founders.get("scorecard_metrics", [])
            if isinstance(m, dict) and m.get("name")
        }
        bc = metrics.get("Bank Cash (Available)")
        assert bc is not None, "Bank Cash (Available) must exist in founders meeting"
        assert bc.get("status") == "manual", (
            f"Bank Cash (Available) status is {bc.get('status')!r}; expected 'manual' "
            f"(no automated source — exec dashboard owns the value)"
        )

    def test_founders_conservative_runway_status_is_manual(self):
        data = _load_yaml(RECESS_OS_YML)
        founders = self._meetings_by_id(data).get("founders") or {}
        metrics = {
            m["name"]: m
            for m in founders.get("scorecard_metrics", [])
            if isinstance(m, dict) and m.get("name")
        }
        cr = metrics.get("Conservative Runway")
        assert cr is not None, "Conservative Runway must exist in founders meeting"
        assert cr.get("status") == "manual", (
            f"Conservative Runway status is {cr.get('status')!r}; expected 'manual'"
        )

    def test_sales_renewal_pipeline_label_is_canonical(self):
        """The legacy display label 'Renewal Bookings Pacing' is misleading —
        the registry_key is 'Renewal Pipeline' (weighted open pipeline).
        Display name must match registry."""
        data = _load_yaml(RECESS_OS_YML)
        sales = self._meetings_by_id(data).get("sales") or {}
        names = [
            m.get("name")
            for m in sales.get("scorecard_metrics", [])
            if isinstance(m, dict)
        ]
        assert "Renewal Pipeline" in names, (
            f"sales scorecard missing 'Renewal Pipeline' — got {names}"
        )
        assert "Renewal Bookings Pacing" not in names, (
            "sales scorecard still has legacy label 'Renewal Bookings Pacing'"
        )

    def test_sales_meeting_has_q_nr_actual_and_forecast(self):
        """Sales scorecard surfaces the Q-internal NR pair (Actual + Forecast).

        Replaces the awkward 'Net Revenue YTD vs Q quota' framing with a
        coherent intra-quarter pair derived from the dashboard forecast engine.
        """
        data = _load_yaml(RECESS_OS_YML)
        sales = self._meetings_by_id(data).get("sales") or {}
        names = [
            m.get("name")
            for m in sales.get("scorecard_metrics", [])
            if isinstance(m, dict)
        ]
        assert "Net Revenue Q (Actual)" in names, (
            f"sales scorecard missing 'Net Revenue Q (Actual)' — got {names}"
        )
        assert "Net Revenue Q (Forecast)" in names, (
            f"sales scorecard missing 'Net Revenue Q (Forecast)' — got {names}"
        )

    def test_leadership_meeting_has_q_nr_actual_and_forecast(self):
        """Leadership pre-read surfaces the same Q-internal NR pair as Sales."""
        data = _load_yaml(RECESS_OS_YML)
        leadership = self._meetings_by_id(data).get("leadership") or {}
        names = [
            m.get("name")
            for m in leadership.get("scorecard_metrics", [])
            if isinstance(m, dict)
        ]
        assert "Net Revenue Q (Actual)" in names, (
            f"leadership scorecard missing 'Net Revenue Q (Actual)' — got {names}"
        )
        assert "Net Revenue Q (Forecast)" in names, (
            f"leadership scorecard missing 'Net Revenue Q (Forecast)' — got {names}"
        )


class TestEngineering3PackSnapshotMigration:
    """Critic-review C2 safety net for the post-snapshot cleanup.

    After the engineering-snapshot migration (dashboard PR #19 + eos commits
    `699582d`/`8acc538`/`1fb71f2`), the 9 engineering metrics flow through the
    standard snapshot pipeline. There is no longer a code-level dispatch table
    (`_LIVE_HANDLERS`/`ENGINEERING_LIVE_METRICS`) pinning the 3 hero metrics —
    everything depends on dashboard registry keeping them as
    `scorecard_status: "automated"` with non-null `snapshot_column`.

    If a future dashboard change reverts either property (e.g., status back
    to `"needs_build"`, or `snapshot_column` to None), all 9 engineering
    metrics silently regress to PHASE2_PLACEHOLDER on Slack/deck/leadership-doc
    and no other test catches it. This test catches the regression at CI.
    """

    W1_HERO_METRICS = ("Features Fully Scoped", "PRDs Generated", "FSDs Generated")
    DISCOVERY_FUNNEL_METRICS = (
        "Discovery Funnel: In Discovery",
        "Discovery Funnel: Discovery Complete",
        "Discovery Funnel: Ready for PRD",
        "Discovery Funnel: PRD In Progress",
        "Discovery Funnel: PRD Proposed",
        "Discovery Funnel: PRD Accepted",
    )

    def test_w1_hero_metrics_are_automated_with_snapshot_column(self):
        """The 3 hero metrics MUST be registered as snapshot-backed automated
        metrics. If dashboard flips this back to needs_build, eos silently
        regresses to '🔨 (Phase 2 migration)' for engineering."""
        from data.metric_registry import METRIC_REGISTRY  # type: ignore

        for metric in self.W1_HERO_METRICS:
            assert metric in METRIC_REGISTRY, (
                f"{metric!r} missing from dashboard METRIC_REGISTRY — eos cron "
                f"will fail contract resolution. Re-check dashboard PR #19."
            )
            entry = METRIC_REGISTRY[metric]
            assert entry.get("scorecard_status") == "automated", (
                f"{metric!r} has scorecard_status={entry.get('scorecard_status')!r}, "
                f"expected 'automated'. Snapshot-driven rendering requires this; "
                f"reverting to 'needs_build' silently regresses to placeholder."
            )
            assert entry.get("snapshot_column"), (
                f"{metric!r} has snapshot_column={entry.get('snapshot_column')!r}, "
                f"expected a non-null column name. The snapshot pipeline reads "
                f"`company_metrics[snapshot_column]`; None means no data flows."
            )

    def test_discovery_funnel_metrics_are_automated_with_snapshot_column(self):
        """Same contract for the 6 Discovery Funnel metrics — they migrated to
        snapshot in the same dashboard PR."""
        from data.metric_registry import METRIC_REGISTRY  # type: ignore

        for metric in self.DISCOVERY_FUNNEL_METRICS:
            assert metric in METRIC_REGISTRY, (
                f"{metric!r} missing from dashboard METRIC_REGISTRY."
            )
            entry = METRIC_REGISTRY[metric]
            assert entry.get("scorecard_status") == "automated", (
                f"{metric!r} has scorecard_status={entry.get('scorecard_status')!r}, "
                f"expected 'automated'."
            )
            assert entry.get("snapshot_column"), (
                f"{metric!r} has snapshot_column={entry.get('snapshot_column')!r}, "
                f"expected a non-null column name."
            )
