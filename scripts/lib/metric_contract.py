"""Metric contract resolution — validates config against the KPI Dashboard registry.

The KPI Dashboard metric_registry.py is GOD. This module:
1. Takes a scorecard metric config from recess_os.yml
2. Looks up the registry_key in metric_registry.py
3. Pulls snapshot_column, format, transform from the REGISTRY (not config)
4. FAILS LOUDLY if the registry_key doesn't exist OR registry entry is malformed
5. FAILS LOUDLY if config tries to override registry-owned logic fields
6. Returns a MetricContract with registry-sourced definitions

If a metric changes in the registry, it automatically changes here.
If a registry_key doesn't match, the build STOPS — no silent degradation.
If the registry entry is missing required fields, the build STOPS.
If config contains forbidden logic fields, the build STOPS.
"""
from dataclasses import dataclass
from typing import Any, Optional


class ContractResolutionError(Exception):
    """Raised when a metric config cannot be resolved against the registry.

    This is a HARD FAILURE. The operator must fix the config or registry
    before any output is generated. No fallbacks. No silent skips.
    """


# Config-side requirements (what LIVES in recess_os.yml)
REQUIRED_CONFIG_FIELDS = ["name", "sensitivity", "status", "null_behavior"]

# Registry-side requirements for automated metrics (fail loud if missing)
REQUIRED_REGISTRY_FIELDS = ["bq_key", "format", "higher_is_better"]

# Fields that config MAY NOT set — they are owned by the registry.
# If a config entry contains any of these, resolution fails loudly. This
# prevents the historical kpi_goals.yml pattern of defining transform math
# in config, which creates a parallel logic engine that drifts from the
# registry over time.
FORBIDDEN_CONFIG_LOGIC_FIELDS = [
    "snapshot_column",
    "snapshot_table",
    "bq_key",
    "format",
    "format_spec",
    "metric_unit",
    "transform",
    "transform_target",
    "transform_baseline",
    "higher_is_better",
    "thresholds",
    "status_update",
]

VALID_SENSITIVITIES = {"public", "leadership", "founders_only"}
VALID_STATUSES = {"automated", "needs_build", "manual", "asana_goal"}
VALID_NULL_BEHAVIORS = {"show_dash", "show_zero", "hide", "show_needs_build"}
VALID_TRANSFORMS = {"raw", "percent_higher_is_better", "percent_lower_is_better"}
VALID_FORMATS = {
    "currency", "percent", "number", "number_millions", "days", "hours",
    "nps", "text", "multiplier", "pipeline_gap", "percent_change", "count",
}


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
    availability_state: str  # derived: "live", "needs_build", "manual"
    asana_goal_id: Optional[str] = None
    notes: Optional[str] = None


def resolve_metric_contract(config: dict, registry: Optional[dict] = None) -> MetricContract:
    """Resolve a scorecard metric config against the KPI Dashboard registry.

    For automated metrics:
    1. Looks up registry_key in the registry
    2. Pulls snapshot_column, format, transform FROM THE REGISTRY (no defaults)
    3. FAILS LOUDLY if registry_key not found
    4. FAILS LOUDLY if registry entry is missing required fields
    5. FAILS LOUDLY if config contains forbidden logic fields

    For needs_build/manual/asana_goal metrics:
    - registry_key is OPTIONAL (they're not wired to BQ yet)
    - BUT if registry_key IS present, it MUST resolve against the registry
      (this enforces that "eventually-automated" metrics stay aligned)
    - These metrics CANNOT enter the automated payload pipeline

    Args:
        config: Metric entry from recess_os.yml scorecard_metrics
        registry: The full METRIC_REGISTRY dict from metric_registry.py.
                  If None, loads it dynamically (for production use).

    Raises:
        ContractResolutionError: HARD FAILURE. Fix config or registry before proceeding.
    """
    # Validate config field requirements
    _validate_config_shape(config)

    # Reject forbidden logic fields regardless of status — config may never
    # redefine registry-owned logic, even for non-automated metrics.
    _reject_forbidden_logic_fields(config)

    status = config["status"]
    sensitivity = config["sensitivity"]
    null_behavior = config["null_behavior"]

    snapshot_column: Optional[str] = None
    format_spec: str = "number"
    transform: str = "raw"

    registry_key = config.get("registry_key")

    if status == "automated":
        # Automated metrics MUST resolve against the registry (no exceptions)
        if not registry_key:
            raise ContractResolutionError(
                f"Automated metric '{config['name']}' has no registry_key. "
                f"Every automated metric MUST point to a metric_registry.py entry."
            )

        reg_entry = _lookup_registry_entry(registry_key, registry)
        _validate_registry_entry(registry_key, reg_entry)

        # Pull definitions FROM THE REGISTRY — no defaults. _validate_registry_entry
        # has already confirmed all REQUIRED_REGISTRY_FIELDS are present and
        # format is in VALID_FORMATS.
        snapshot_column = reg_entry["bq_key"]
        format_spec = reg_entry["format"]
        higher_is_better = reg_entry["higher_is_better"]

        # For automated metrics, bq_key MUST be non-null — a null bq_key
        # means "this metric is computed live, not snapshot-backed," and
        # the canonical payload layer cannot consume it. Such metrics must
        # be marked needs_build until the snapshot column exists.
        if snapshot_column is None:
            raise ContractResolutionError(
                f"Automated metric '{config['name']}' (registry_key='{registry_key}') "
                f"has bq_key=None in the registry. The canonical payload layer reads "
                f"kpi_daily_snapshot; a metric without a snapshot column cannot be "
                f"automated. Mark status: needs_build until the snapshot column exists."
            )

        # Derive transform from registry's higher_is_better.
        # If higher_is_better is True and a target exists → percent_higher_is_better
        # If higher_is_better is False and a target exists → percent_lower_is_better
        # If no target → raw (display-only, no goal tracking)
        # Note: _validate_registry_entry already rejected None higher_is_better,
        # so here it's always True or False.
        if config.get("target") is not None:
            transform = "percent_higher_is_better" if higher_is_better else "percent_lower_is_better"
        else:
            transform = "raw"

    else:
        # Non-automated metrics (needs_build, manual, asana_goal):
        # If they HAVE a registry_key, it must still resolve (keeps the
        # "eventually automated" path aligned with the registry). If they
        # DON'T have a registry_key, the fields stay at safe defaults and
        # the metric CANNOT enter the automated payload pipeline.
        if registry_key:
            reg_entry = _lookup_registry_entry(registry_key, registry)
            _validate_registry_entry(registry_key, reg_entry)
            # Still pull format_spec so downstream display rendering is consistent
            format_spec = reg_entry["format"]
            snapshot_column = reg_entry["bq_key"]  # may be None, OK for non-automated

    # Derive availability_state — strict map, no default
    availability_map = {
        "automated": "live",
        "needs_build": "needs_build",
        "manual": "manual",
        "asana_goal": "asana_goal",
    }
    if status not in availability_map:
        # Should be impossible after _validate_config_shape, but fail loud if it happens
        raise ContractResolutionError(
            f"Metric '{config['name']}' has unmappable status '{status}' "
            f"(validation bypassed — this is a bug)."
        )

    return MetricContract(
        metric_name=config["name"],
        registry_key=registry_key,
        snapshot_column=snapshot_column,
        target=config.get("target"),
        transform=transform,
        format_spec=format_spec,
        sensitivity=sensitivity,
        status=status,
        null_behavior=null_behavior,
        availability_state=availability_map[status],
        asana_goal_id=config.get("asana_goal_id"),
        notes=config.get("notes"),
    )


def _validate_config_shape(config: dict) -> None:
    """Raise if config is missing required fields or has invalid enum values."""
    missing = [f for f in REQUIRED_CONFIG_FIELDS if f not in config or config[f] is None]
    if missing:
        raise ContractResolutionError(
            f"Metric '{config.get('name', '?')}' missing required config fields: {missing}"
        )

    status = config["status"]
    if status not in VALID_STATUSES:
        raise ContractResolutionError(
            f"Metric '{config['name']}' has invalid status '{status}'. Valid: {sorted(VALID_STATUSES)}"
        )

    sensitivity = config["sensitivity"]
    if sensitivity not in VALID_SENSITIVITIES:
        raise ContractResolutionError(
            f"Metric '{config['name']}' has invalid sensitivity '{sensitivity}'. "
            f"Valid: {sorted(VALID_SENSITIVITIES)}"
        )

    null_behavior = config["null_behavior"]
    if null_behavior not in VALID_NULL_BEHAVIORS:
        raise ContractResolutionError(
            f"Metric '{config['name']}' has invalid null_behavior '{null_behavior}'. "
            f"Valid: {sorted(VALID_NULL_BEHAVIORS)}"
        )


def _reject_forbidden_logic_fields(config: dict) -> None:
    """Raise if config contains any registry-owned logic fields.

    This prevents config from becoming a parallel logic engine. The registry
    is the ONLY place where snapshot columns, formats, transforms, and
    higher_is_better direction are defined.
    """
    violations = [f for f in FORBIDDEN_CONFIG_LOGIC_FIELDS if f in config]
    if violations:
        raise ContractResolutionError(
            f"Metric '{config.get('name', '?')}' has forbidden logic fields in config: "
            f"{violations}. These fields are owned by the KPI Dashboard metric_registry.py "
            f"and cannot be set in recess_os.yml. Remove them from config and rely on "
            f"registry_key lookup."
        )


def _lookup_registry_entry(registry_key: str, registry: Optional[dict]) -> dict:
    """Find a registry entry by key, loading the registry if needed. Fail loud on miss."""
    if registry is None:
        registry = _load_registry()

    if registry_key not in registry:
        raise ContractResolutionError(
            f"Metric registry_key '{registry_key}' does NOT exist in metric_registry.py. "
            f"Fix the registry_key or add the metric to the registry. "
            f"This is a HARD FAILURE — no fallback, no skip."
        )

    entry = registry[registry_key]

    # Deprecation check — Constraint 6: registry keys are immutable, but
    # deprecated entries must redirect explicitly.
    if entry.get("deprecated"):
        replaced_by = entry.get("replaced_by", "unknown")
        raise ContractResolutionError(
            f"Metric '{registry_key}' is DEPRECATED in the registry. "
            f"Update config to use '{replaced_by}' instead."
        )

    return entry


def _validate_registry_entry(registry_key: str, reg_entry: dict) -> None:
    """Raise if a registry entry is missing required fields or has invalid values.

    No silent defaults for contract-critical fields. If the registry is
    malformed for this key, the build stops before any output is generated.
    """
    for field in REQUIRED_REGISTRY_FIELDS:
        if field not in reg_entry:
            raise ContractResolutionError(
                f"Registry entry '{registry_key}' is missing required field '{field}'. "
                f"The registry schema requires {REQUIRED_REGISTRY_FIELDS} for every "
                f"metric. Fix metric_registry.py."
            )

    # bq_key MAY be None for computed metrics — that's enforced at the
    # automated-metric level, not here. But format and higher_is_better
    # must be non-null regardless.
    if reg_entry["format"] is None:
        raise ContractResolutionError(
            f"Registry entry '{registry_key}' has format=None. Every metric must "
            f"specify a format. Fix metric_registry.py."
        )

    if reg_entry["format"] not in VALID_FORMATS:
        raise ContractResolutionError(
            f"Registry entry '{registry_key}' has invalid format '{reg_entry['format']}'. "
            f"Valid formats: {sorted(VALID_FORMATS)}. Fix metric_registry.py."
        )

    if reg_entry["higher_is_better"] is None:
        raise ContractResolutionError(
            f"Registry entry '{registry_key}' has higher_is_better=None. "
            f"Every metric must declare direction (True or False). Fix metric_registry.py. "
            f"If the metric is genuinely directionless, mark it as a display-only metric "
            f"with status: manual in recess_os.yml."
        )

    if not isinstance(reg_entry["higher_is_better"], bool):
        raise ContractResolutionError(
            f"Registry entry '{registry_key}' has higher_is_better="
            f"{reg_entry['higher_is_better']!r} (type {type(reg_entry['higher_is_better']).__name__}). "
            f"Must be True or False. Fix metric_registry.py."
        )


# ---- Registry cache ---------------------------------------------------------
# _load_registry() is called many times per cron run. Import/exec of the
# registry file is expensive and unnecessary after the first call. Cache it.

_REGISTRY_CACHE: Optional[dict] = None


def _load_registry() -> dict:
    """Load the KPI Dashboard metric registry from its canonical location.

    This is the GOD import — metric_registry.py is the single source of truth.
    Cached after first load. Use clear_registry_cache() in tests to reset.
    """
    global _REGISTRY_CACHE
    if _REGISTRY_CACHE is not None:
        return _REGISTRY_CACHE

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
    try:
        spec.loader.exec_module(module)
    except Exception as e:
        raise ContractResolutionError(
            f"Failed to import metric_registry.py: {type(e).__name__}: {e}"
        ) from e

    if not hasattr(module, "METRIC_REGISTRY"):
        raise ContractResolutionError(
            f"metric_registry.py at {registry_path} does not export METRIC_REGISTRY. "
            f"The variable may have been renamed. This is the GOD import — it must exist."
        )

    registry = module.METRIC_REGISTRY
    if not isinstance(registry, dict) or not registry:
        raise ContractResolutionError(
            f"metric_registry.py exports METRIC_REGISTRY but it is empty or not a dict. "
            f"Got {type(registry).__name__}."
        )

    _REGISTRY_CACHE = registry
    return _REGISTRY_CACHE


def clear_registry_cache() -> None:
    """Reset the cached registry. Use in tests to force a fresh load."""
    global _REGISTRY_CACHE
    _REGISTRY_CACHE = None
