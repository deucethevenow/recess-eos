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
        assert contract.availability_state == "asana_goal"
        assert contract.asana_goal_id == "1213958752860959"


class TestRegistrySchemaValidation:
    """Hardening B: registry entries must have all required fields. No silent defaults."""

    def _base_config(self):
        return {
            "name": "Test Metric",
            "registry_key": "Test Metric",
            "target": 100,
            "sensitivity": "public",
            "status": "automated",
            "null_behavior": "show_dash",
        }

    def test_missing_bq_key_in_registry_raises(self):
        """Registry entry without bq_key → hard failure."""
        registry = {"Test Metric": {"format": "currency", "higher_is_better": True}}
        with pytest.raises(ContractResolutionError, match="missing required field 'bq_key'"):
            resolve_metric_contract(self._base_config(), registry=registry)

    def test_missing_format_in_registry_raises(self):
        """Registry entry without format → hard failure (no silent 'number' default)."""
        registry = {"Test Metric": {"bq_key": "test_col", "higher_is_better": True}}
        with pytest.raises(ContractResolutionError, match="missing required field 'format'"):
            resolve_metric_contract(self._base_config(), registry=registry)

    def test_missing_higher_is_better_raises(self):
        """Registry entry without higher_is_better → hard failure (no silent True default)."""
        registry = {"Test Metric": {"bq_key": "test_col", "format": "currency"}}
        with pytest.raises(ContractResolutionError, match="missing required field 'higher_is_better'"):
            resolve_metric_contract(self._base_config(), registry=registry)

    def test_higher_is_better_none_raises(self):
        """Registry entry with higher_is_better=None → hard failure."""
        registry = {"Test Metric": {"bq_key": "test_col", "format": "currency", "higher_is_better": None}}
        with pytest.raises(ContractResolutionError, match="higher_is_better=None"):
            resolve_metric_contract(self._base_config(), registry=registry)

    def test_higher_is_better_non_bool_raises(self):
        """Registry entry with higher_is_better='yes' (string) → hard failure."""
        registry = {"Test Metric": {"bq_key": "test_col", "format": "currency", "higher_is_better": "yes"}}
        with pytest.raises(ContractResolutionError, match="higher_is_better="):
            resolve_metric_contract(self._base_config(), registry=registry)

    def test_format_none_raises(self):
        """Registry entry with format=None → hard failure."""
        registry = {"Test Metric": {"bq_key": "test_col", "format": None, "higher_is_better": True}}
        with pytest.raises(ContractResolutionError, match="format=None"):
            resolve_metric_contract(self._base_config(), registry=registry)

    def test_invalid_format_value_raises(self):
        """Registry entry with format not in VALID_FORMATS → hard failure."""
        registry = {"Test Metric": {"bq_key": "test_col", "format": "flibbertigibbet", "higher_is_better": True}}
        with pytest.raises(ContractResolutionError, match="invalid format"):
            resolve_metric_contract(self._base_config(), registry=registry)

    def test_automated_metric_with_null_bq_key_raises(self):
        """Automated metric pointing to entry with bq_key=None → hard failure.

        Such metrics must be marked needs_build until a snapshot column exists.
        The canonical payload layer only reads kpi_daily_snapshot.
        """
        registry = {"Test Metric": {"bq_key": None, "format": "currency", "higher_is_better": True}}
        with pytest.raises(ContractResolutionError, match="no snapshot column"):
            resolve_metric_contract(self._base_config(), registry=registry)

    def test_deprecated_metric_raises(self):
        """Registry entry marked deprecated → hard failure pointing to replacement."""
        registry = {
            "Old Metric": {
                "bq_key": "old_col",
                "format": "currency",
                "higher_is_better": True,
                "deprecated": True,
                "replaced_by": "New Metric",
            }
        }
        config = self._base_config()
        config["name"] = "Old Metric"
        config["registry_key"] = "Old Metric"
        with pytest.raises(ContractResolutionError, match="DEPRECATED.*use 'New Metric'"):
            resolve_metric_contract(config, registry=registry)


class TestForbiddenConfigLogicFields:
    """Hardening B: config may not redefine registry-owned logic fields."""

    def _base_config(self):
        return {
            "name": "Pipeline Coverage",
            "registry_key": "Pipeline Coverage",
            "target": 2.5,
            "sensitivity": "public",
            "status": "automated",
            "null_behavior": "show_dash",
        }

    def test_config_with_snapshot_column_raises(self):
        config = self._base_config()
        config["snapshot_column"] = "pipeline_coverage"
        with pytest.raises(ContractResolutionError, match="forbidden logic fields.*snapshot_column"):
            resolve_metric_contract(config, registry=MOCK_REGISTRY)

    def test_config_with_format_raises(self):
        config = self._base_config()
        config["format"] = "multiplier"
        with pytest.raises(ContractResolutionError, match="forbidden logic fields.*format"):
            resolve_metric_contract(config, registry=MOCK_REGISTRY)

    def test_config_with_transform_raises(self):
        config = self._base_config()
        config["transform"] = "raw"
        with pytest.raises(ContractResolutionError, match="forbidden logic fields.*transform"):
            resolve_metric_contract(config, registry=MOCK_REGISTRY)

    def test_config_with_transform_baseline_raises(self):
        """kpi_goals.yml legacy fields must be rejected."""
        config = self._base_config()
        config["transform_baseline"] = 60
        with pytest.raises(ContractResolutionError, match="forbidden logic fields.*transform_baseline"):
            resolve_metric_contract(config, registry=MOCK_REGISTRY)

    def test_config_with_transform_target_raises(self):
        config = self._base_config()
        config["transform_target"] = 0.50
        with pytest.raises(ContractResolutionError, match="forbidden logic fields.*transform_target"):
            resolve_metric_contract(config, registry=MOCK_REGISTRY)

    def test_config_with_thresholds_raises(self):
        """Legacy kpi_goals.yml threshold logic is banned in config."""
        config = self._base_config()
        config["thresholds"] = [{"if": "value > 10", "status": "achieved"}]
        with pytest.raises(ContractResolutionError, match="forbidden logic fields.*thresholds"):
            resolve_metric_contract(config, registry=MOCK_REGISTRY)

    def test_config_with_higher_is_better_raises(self):
        config = self._base_config()
        config["higher_is_better"] = True
        with pytest.raises(ContractResolutionError, match="forbidden logic fields.*higher_is_better"):
            resolve_metric_contract(config, registry=MOCK_REGISTRY)

    def test_forbidden_fields_rejected_for_non_automated_too(self):
        """needs_build metrics with logic fields still get rejected."""
        config = {
            "name": "Future Metric",
            "registry_key": None,
            "target": 100,
            "sensitivity": "public",
            "status": "needs_build",
            "null_behavior": "show_needs_build",
            "transform": "raw",  # forbidden
        }
        with pytest.raises(ContractResolutionError, match="forbidden logic fields"):
            resolve_metric_contract(config, registry=MOCK_REGISTRY)


class TestNonAutomatedMetricValidation:
    """Hardening B: needs_build/manual metrics with registry_key still validate."""

    def test_needs_build_with_bad_registry_key_raises(self):
        """needs_build with a registry_key that doesn't exist → hard failure."""
        config = {
            "name": "Eventually Automated",
            "registry_key": "Does Not Exist",
            "target": 100,
            "sensitivity": "public",
            "status": "needs_build",
            "null_behavior": "show_needs_build",
        }
        with pytest.raises(ContractResolutionError, match="does NOT exist"):
            resolve_metric_contract(config, registry=MOCK_REGISTRY)

    def test_needs_build_with_valid_registry_key_ok(self):
        """needs_build with valid registry_key succeeds (aligns with eventual automation)."""
        config = {
            "name": "Pipeline Coverage Preview",
            "registry_key": "Pipeline Coverage",
            "target": 2.5,
            "sensitivity": "public",
            "status": "needs_build",
            "null_behavior": "show_needs_build",
        }
        contract = resolve_metric_contract(config, registry=MOCK_REGISTRY)
        assert contract.availability_state == "needs_build"
        assert contract.format_spec == "multiplier"  # resolved from registry


class TestRegistryCache:
    """Hardening B: registry is cached after first load."""

    def test_cache_survives_multiple_calls(self, monkeypatch):
        """Second call to _load_registry returns the same dict without re-importing."""
        from lib import metric_contract

        metric_contract.clear_registry_cache()

        call_count = {"n": 0}

        def fake_load():
            call_count["n"] += 1
            return {"Test": {"bq_key": "t", "format": "currency", "higher_is_better": True}}

        # Prime cache directly
        metric_contract._REGISTRY_CACHE = None

        # First call loads, second call uses cache
        reg1 = {"Test": {"bq_key": "t", "format": "currency", "higher_is_better": True}}
        metric_contract._REGISTRY_CACHE = reg1

        assert metric_contract._load_registry() is reg1
        assert metric_contract._load_registry() is reg1  # same object

        metric_contract.clear_registry_cache()
        assert metric_contract._REGISTRY_CACHE is None


class TestSnapshotColumnResolution:
    """Tests for snapshot_column vs bq_key resolution in resolve_metric_contract."""

    def test_snapshot_column_preferred_over_bq_key(self):
        """When registry has snapshot_column, it's used instead of bq_key."""
        registry = {
            "Demand NRR": {
                "bq_key": "nrr",                   # internal dashboard key
                "snapshot_column": "demand_nrr",    # actual BQ column
                "format": "percent",
                "higher_is_better": True,
            },
        }
        config = {
            "name": "Demand NRR", "registry_key": "Demand NRR",
            "target": 0.50, "sensitivity": "public",
            "status": "automated", "null_behavior": "show_dash",
        }
        contract = resolve_metric_contract(config, registry=registry)
        assert contract.snapshot_column == "demand_nrr"  # snapshot_column, NOT bq_key

    def test_explicit_none_snapshot_column_does_not_fallback(self):
        """snapshot_column=None means 'no snapshot column' — should NOT fall back to bq_key.

        This triggers the 'automated metric has no snapshot column' error,
        because explicitly setting snapshot_column=None means the metric is
        live-computed and cannot be automated via the snapshot pipeline.
        """
        registry = {
            "Weighted Pipeline": {
                "bq_key": "weighted_pipeline_internal",  # internal key, NOT a snapshot column
                "snapshot_column": None,                  # explicit: no snapshot column
                "format": "currency",
                "higher_is_better": True,
            },
        }
        config = {
            "name": "Weighted Pipeline", "registry_key": "Weighted Pipeline",
            "target": None, "sensitivity": "public",
            "status": "automated", "null_behavior": "show_dash",
        }
        with pytest.raises(ContractResolutionError, match="snapshot column"):
            resolve_metric_contract(config, registry=registry)

    def test_missing_snapshot_column_falls_back_to_bq_key(self):
        """Legacy registry without snapshot_column field → fall back to bq_key."""
        registry = {
            "Pipeline Coverage": {
                "bq_key": "pipeline_coverage",
                # no snapshot_column key at all
                "format": "multiplier",
                "higher_is_better": True,
            },
        }
        config = {
            "name": "Pipeline Coverage", "registry_key": "Pipeline Coverage",
            "target": 2.5, "sensitivity": "public",
            "status": "automated", "null_behavior": "show_dash",
        }
        contract = resolve_metric_contract(config, registry=registry)
        assert contract.snapshot_column == "pipeline_coverage"  # bq_key used as fallback
