"""Tests for metric contract resolution — validates config against the registry.

The KPI Dashboard metric_registry.py is GOD. These tests verify:
1. Automated metrics MUST resolve against the registry
2. Missing registry_key → HARD FAIL (not silent skip)
3. Registry provides snapshot_column, format, transform — config does NOT
4. needs_build and asana_goal metrics skip registry lookup (they don't use it yet)
"""
import pytest
from lib.metric_contract import resolve_metric_contract, MetricContract, ContractResolutionError


# Mock registry that simulates metric_registry.py entries
MOCK_REGISTRY = {
    "Pipeline Coverage": {
        "bq_key": "pipeline_coverage",
        "format": "multiplier",
        "higher_is_better": True,
    },
    "Demand NRR": {
        "bq_key": "demand_nrr",
        "format": "percent",
        "higher_is_better": True,
    },
    "Days to Fulfill": {
        "bq_key": "time_to_fulfill_days",
        "format": "days",
        "higher_is_better": False,
    },
}


class TestRegistryLookup:
    def test_automated_metric_resolves_from_registry(self):
        """Config points to registry_key, contract gets snapshot_column + format FROM registry."""
        config = {
            "name": "Pipeline Coverage",
            "registry_key": "Pipeline Coverage",
            "target": 2.5,
            "sensitivity": "public",
            "status": "automated",
            "null_behavior": "show_dash",
            # NOTE: NO snapshot_column, format, transform in config
        }
        contract = resolve_metric_contract(config, registry=MOCK_REGISTRY)
        assert contract.snapshot_column == "pipeline_coverage"  # FROM REGISTRY
        assert contract.format_spec == "multiplier"  # FROM REGISTRY
        assert contract.transform == "percent_higher_is_better"  # DERIVED from registry higher_is_better + target

    def test_lower_is_better_metric_gets_correct_transform(self):
        """Days to Fulfill has higher_is_better=False → percent_lower_is_better."""
        config = {
            "name": "Days to Fulfill",
            "registry_key": "Days to Fulfill",
            "target": 30,
            "sensitivity": "public",
            "status": "automated",
            "null_behavior": "show_dash",
        }
        contract = resolve_metric_contract(config, registry=MOCK_REGISTRY)
        assert contract.transform == "percent_lower_is_better"  # FROM REGISTRY

    def test_no_target_means_raw_transform(self):
        """Without a target, transform is 'raw' even if registry has higher_is_better."""
        config = {
            "name": "NRR Display",
            "registry_key": "Demand NRR",
            "target": None,
            "sensitivity": "public",
            "status": "automated",
            "null_behavior": "show_dash",
        }
        contract = resolve_metric_contract(config, registry=MOCK_REGISTRY)
        assert contract.transform == "raw"


class TestHardFailures:
    def test_missing_registry_key_raises(self):
        """Automated metric with registry_key not in registry → HARD FAIL."""
        config = {
            "name": "Fake Metric",
            "registry_key": "This Does Not Exist",
            "target": 100,
            "sensitivity": "public",
            "status": "automated",
            "null_behavior": "show_dash",
        }
        with pytest.raises(ContractResolutionError, match="does NOT exist in metric_registry"):
            resolve_metric_contract(config, registry=MOCK_REGISTRY)

    def test_no_registry_key_for_automated_raises(self):
        """Automated metric with no registry_key at all → HARD FAIL."""
        config = {
            "name": "No Key Metric",
            "registry_key": None,
            "sensitivity": "public",
            "status": "automated",
            "null_behavior": "show_dash",
        }
        with pytest.raises(ContractResolutionError, match="no registry_key"):
            resolve_metric_contract(config, registry=MOCK_REGISTRY)

    def test_missing_config_fields_raises(self):
        """Missing required config fields → HARD FAIL."""
        config = {"name": "Bad Metric"}  # missing sensitivity, status, null_behavior
        with pytest.raises(ContractResolutionError, match="missing required"):
            resolve_metric_contract(config, registry=MOCK_REGISTRY)

    def test_invalid_sensitivity_raises(self):
        """Invalid sensitivity value → HARD FAIL."""
        config = {
            "name": "Bad Sensitivity",
            "registry_key": "Pipeline Coverage",
            "sensitivity": "top_secret",
            "status": "automated",
            "null_behavior": "show_dash",
        }
        with pytest.raises(ContractResolutionError, match="invalid sensitivity"):
            resolve_metric_contract(config, registry=MOCK_REGISTRY)

    def test_invalid_null_behavior_raises(self):
        """Invalid null_behavior value → HARD FAIL."""
        config = {
            "name": "Bad Null",
            "registry_key": "Pipeline Coverage",
            "sensitivity": "public",
            "status": "automated",
            "null_behavior": "crash_and_burn",
        }
        with pytest.raises(ContractResolutionError, match="invalid null_behavior"):
            resolve_metric_contract(config, registry=MOCK_REGISTRY)


class TestNonAutomatedMetrics:
    def test_needs_build_skips_registry(self):
        """needs_build metrics don't need a registry_key — they're not wired yet."""
        config = {
            "name": "Offer fulfillment speed",
            "registry_key": None,
            "target": 30,
            "sensitivity": "public",
            "status": "needs_build",
            "null_behavior": "show_needs_build",
        }
        contract = resolve_metric_contract(config, registry=MOCK_REGISTRY)
        assert contract.availability_state == "needs_build"
        assert contract.snapshot_column is None

    def test_manual_skips_registry(self):
        """manual metrics don't need a registry_key — operator enters values by hand."""
        config = {
            "name": "Customer satisfaction",
            "registry_key": None,
            "target": 90,
            "sensitivity": "public",
            "status": "manual",
            "null_behavior": "show_dash",
        }
        contract = resolve_metric_contract(config, registry=MOCK_REGISTRY)
        assert contract.availability_state == "manual"
        assert contract.snapshot_column is None

    def test_asana_goal_skips_registry(self):
        """asana_goal metrics get progress from Asana, not from the registry."""
        config = {
            "name": "Dept AI plans completed",
            "registry_key": None,
            "target": 5,
            "sensitivity": "public",
            "status": "asana_goal",
            "asana_goal_id": "1213958752860959",
            "null_behavior": "show_dash",
        }
        contract = resolve_metric_contract(config, registry=MOCK_REGISTRY)
        assert contract.status == "asana_goal"
        assert contract.asana_goal_id == "1213958752860959"
