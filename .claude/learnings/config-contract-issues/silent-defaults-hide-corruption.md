---
module: Config/Contract
date: 2026-04-11
problem_type: silent_default_corruption
component: metric_contract
symptoms: ["Metric rendered as raw float in Slack", "Missing format field silently defaulted to None", "higher_is_better returned wrong direction indicator"]
root_cause: silent_degradation
severity: critical
tags: [silent, defaults, get, contract, format, higher_is_better, fail-loud]
affected_files: [scripts/lib/metric_contract.py, scripts/lib/metric_payloads.py]
resolution_type: code_fix
elevated_to_critical: true
---
# Never use .get() defaults for contract-critical fields

## What the agent does wrong

Uses `.get(field, default)` for fields that MUST exist in the registry:

```python
# WRONG — hides missing format field, renders raw float
format_str = registry_entry.get("format", None)
# Renders: "NRR: 0.6512" instead of "NRR: 65.1%"

# WRONG — wrong default direction, no one notices
higher_is_better = registry_entry.get("higher_is_better", True)
# A metric where lower IS better silently shows green arrows for bad values
```

## Why it's wrong

Silent defaults mask schema corruption. When a registry entry is missing `format` or `higher_is_better`, that's a DATA BUG that needs to be fixed in `metric_registry.py` — not papered over with a default value. The silent degradation means no one notices the problem until a stakeholder asks "why does the Slack post show 0.6512 instead of 65.1%?"

## Correct pattern

```python
# RIGHT — fail loud on missing contract-critical fields
format_str = registry_entry["format"]  # KeyError if missing → ContractResolutionError
higher_is_better = registry_entry["higher_is_better"]  # same

# RIGHT — explicit validation in contract resolution
if "format" not in registry_entry:
    raise ContractResolutionError(f"Missing 'format' for {registry_key}")
```

## Prevention

- Remove all `.get()` defaults for contract-critical fields: format, higher_is_better, bq_key
- `metric_contract.py` validates presence of all required fields during resolution
- Any new metric must have all fields populated in `metric_registry.py` before wiring into EOS
