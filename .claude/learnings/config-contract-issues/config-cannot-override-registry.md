---
module: Config/Contract
date: 2026-04-11
problem_type: config_logic_duplication
component: config_yml
symptoms: ["Agent added transform field to recess_os.yml", "Config contained format or higher_is_better", "Duplicate logic between config and registry"]
root_cause: registry_override
severity: critical
tags: [registry, config, transform, format, higher_is_better, contract, forbidden]
affected_files: [config/recess_os.yml, scripts/lib/metric_contract.py]
resolution_type: code_fix
elevated_to_critical: true
---
# Never put logic fields in recess_os.yml

## What the agent does wrong

Adds transform, format, or higher_is_better fields to goal/metric entries in `recess_os.yml`:

```yaml
# WRONG — these fields belong in metric_registry.py, not config
goals:
  - registry_key: net_revenue_retention
    target: 1.0
    transform: "multiply_100"        # ← FORBIDDEN
    format: "{:.1f}%"               # ← FORBIDDEN
    higher_is_better: true           # ← FORBIDDEN
```

## Why it's wrong

`kpi_goals.yml` was a parallel logic engine that contained these fields and drifted from `metric_registry.py` (the actual source of truth in the KPI Dashboard). It was deprecated entirely and set to `kpi_goals: []`.

`metric_contract.py` now has `FORBIDDEN_CONFIG_LOGIC_FIELDS` that raises `ContractResolutionError` if any of these fields appear in config. `test_kpi_config_consistency.py` is the drift guard.

## Correct pattern

```yaml
# RIGHT — pointer-only entry in recess_os.yml
goals:
  - registry_key: net_revenue_retention
    asana_goal_id: "1234567890"
    target: 1.0
    sensitivity: leadership
    status: automated
    null_behavior: skip
```

All logic (transform, format, higher_is_better) comes from `metric_registry.py` via contract resolution in `metric_contract.py`.

## Prevention

- `FORBIDDEN_CONFIG_LOGIC_FIELDS` in `metric_contract.py` enforces this at runtime
- `test_kpi_config_consistency.py` catches drift in CI
- CLAUDE.md documents this as "Registry is GOD" principle
