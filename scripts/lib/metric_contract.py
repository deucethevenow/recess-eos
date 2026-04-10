"""Metric contract resolution — validates config against the KPI Dashboard registry.

The KPI Dashboard metric_registry.py is GOD. This module:
1. Takes a scorecard metric config from recess_os.yml
2. Looks up the registry_key in metric_registry.py
3. Pulls snapshot_column, format, transform from the REGISTRY (not config)
4. FAILS LOUDLY if the registry_key doesn't exist
5. Returns a MetricContract with registry-sourced definitions

If a metric changes in the registry, it automatically changes here.
If a registry_key doesn't match, the build STOPS — no silent degradation.
"""
from dataclasses import dataclass
from typing import Any, Optional


class ContractResolutionError(Exception):
    """Raised when a metric config cannot be resolved against the registry.

    This is a HARD FAILURE. The operator must fix the config or registry
    before any output is generated. No fallbacks. No silent skips.
    """


REQUIRED_CONFIG_FIELDS = ["name", "sensitivity", "status", "null_behavior"]
# NOTE: snapshot_column, format, transform are NOT in config — they come from the registry
VALID_SENSITIVITIES = {"public", "leadership", "founders_only"}
VALID_STATUSES = {"automated", "needs_build", "manual", "asana_goal"}
VALID_NULL_BEHAVIORS = {"show_dash", "show_zero", "hide", "show_needs_build"}
VALID_TRANSFORMS = {"raw", "percent_higher_is_better", "percent_lower_is_better"}


@dataclass(frozen=True)
class MetricContract:
    metric_name: str
    registry_key: Optional[str]
    snapshot_column: Optional[str]
    target: Optional[float]
    transform: str
    format_spec: str
    sensitivity: str
    status: str
    null_behavior: str
    availability_state: str  # derived: "live", "needs_build", "manual", "error"
    asana_goal_id: Optional[str] = None
    notes: Optional[str] = None


def resolve_metric_contract(config: dict, registry: dict[str, Any] = None) -> MetricContract:
    """Resolve a scorecard metric config against the KPI Dashboard registry.

    For automated metrics:
    1. Looks up registry_key in the registry
    2. Pulls snapshot_column, format, transform FROM THE REGISTRY
    3. FAILS LOUDLY if registry_key not found

    Args:
        config: Metric entry from recess_os.yml scorecard_metrics
        registry: The full METRIC_REGISTRY dict from metric_registry.py.
                  If None, loads it dynamically (for production use).

    Raises:
        ContractResolutionError: HARD FAILURE. Fix config or registry before proceeding.
    """
    # Check required config fields (the ones that LIVE in config, not registry)
    missing = [f for f in REQUIRED_CONFIG_FIELDS if f not in config or config[f] is None]
    if missing:
        raise ContractResolutionError(
            f"Metric '{config.get('name', '?')}' missing required config fields: {missing}"
        )

    status = config["status"]
    if status not in VALID_STATUSES:
        raise ContractResolutionError(
            f"Metric '{config['name']}' has invalid status '{status}'. Valid: {VALID_STATUSES}"
        )

    sensitivity = config["sensitivity"]
    if sensitivity not in VALID_SENSITIVITIES:
        raise ContractResolutionError(
            f"Metric '{config['name']}' has invalid sensitivity '{sensitivity}'. Valid: {VALID_SENSITIVITIES}"
        )

    null_behavior = config["null_behavior"]
    if null_behavior not in VALID_NULL_BEHAVIORS:
        raise ContractResolutionError(
            f"Metric '{config['name']}' has invalid null_behavior '{null_behavior}'. Valid: {VALID_NULL_BEHAVIORS}"
        )

    # For automated metrics: RESOLVE FROM REGISTRY (the hard guarantee)
    snapshot_column = None
    format_spec = "number"
    transform = "raw"

    if status == "automated":
        registry_key = config.get("registry_key")
        if not registry_key:
            raise ContractResolutionError(
                f"Automated metric '{config['name']}' has no registry_key. "
                f"Every automated metric MUST point to a metric_registry.py entry."
            )

        # Load registry if not provided
        if registry is None:
            registry = _load_registry()

        if registry_key not in registry:
            raise ContractResolutionError(
                f"Metric '{config['name']}' has registry_key '{registry_key}' "
                f"which does NOT exist in metric_registry.py. "
                f"Fix the registry_key or add the metric to the registry. "
                f"This is a HARD FAILURE — no fallback, no skip."
            )

        reg_entry = registry[registry_key]

        # Pull definitions FROM THE REGISTRY — config does NOT override these
        snapshot_column = reg_entry.get("bq_key")  # registry calls it bq_key
        format_spec = reg_entry.get("format", "number")

        # Derive transform from registry's higher_is_better field
        higher_is_better = reg_entry.get("higher_is_better", True)
        if config.get("target") is not None:
            # If there's a target, we need a percentage transform for Asana Goals
            transform = "percent_higher_is_better" if higher_is_better else "percent_lower_is_better"
        else:
            transform = "raw"

        # snapshot_column can be None if the registry metric is computed (not in snapshot)
        # That's OK — it means this metric uses a live query path, not snapshot

    # Derive availability_state
    availability_map = {
        "automated": "live",
        "needs_build": "needs_build",
        "manual": "manual",
        "asana_goal": "live",
    }

    return MetricContract(
        metric_name=config["name"],
        registry_key=config.get("registry_key"),
        snapshot_column=snapshot_column,
        target=config.get("target"),
        transform=transform,
        format_spec=format_spec,
        sensitivity=sensitivity,
        status=status,
        null_behavior=null_behavior,
        availability_state=availability_map.get(status, "error"),
        asana_goal_id=config.get("asana_goal_id"),
        notes=config.get("notes"),
    )


def _load_registry() -> dict[str, Any]:
    """Load the KPI Dashboard metric registry from its canonical location.

    This is the GOD import — metric_registry.py is the single source of truth.
    """
    import importlib.util
    from pathlib import Path

    registry_path = Path("~/Projects/company-kpi-dashboard/dashboard/data/metric_registry.py").expanduser()
    if not registry_path.exists():
        raise ContractResolutionError(
            f"metric_registry.py not found at {registry_path}. "
            f"The KPI Dashboard registry is the single source of truth for all metric definitions."
        )

    spec = importlib.util.spec_from_file_location("metric_registry", registry_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    return getattr(module, "METRIC_REGISTRY", {})
