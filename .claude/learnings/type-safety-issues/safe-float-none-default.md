---
module: NaN Safety
date: 2026-04-11
problem_type: type_contract_violation
component: nan_safety
symptoms: ["safe_float returned None instead of float", "Downstream arithmetic failed on None", "Type checker flagged Optional[float] mismatch"]
root_cause: type_signature_violation
severity: high
tags: [safe_float, type_contract, optional, none, nan_safety, float]
affected_files: [scripts/lib/nan_safety.py, scripts/lib/metric_payloads.py]
resolution_type: code_fix
elevated_to_critical: true
---
# Never pass default=None to safe_float()

## What the agent does wrong

Passes `default=None` to `safe_float()` when the caller needs a nullable return:

```python
# WRONG — safe_float() signature returns float, not Optional[float]
value = safe_float(raw_value, default=None)
# downstream: value * 100  → TypeError: unsupported operand type(s) for *: 'NoneType' and 'int'
```

## Why it's wrong

`safe_float()` has a return type of `float` with a default of `0.0`. Passing `default=None` makes it return `Optional[float]`, which violates the type contract. Downstream code that assumes a float (arithmetic, formatting) will crash on None.

## Correct pattern

```python
# RIGHT — use the sibling function for nullable values
value = _safe_optional_float(raw_value)  # returns Optional[float]

# RIGHT — if you need a guaranteed float, use the default
value = safe_float(raw_value)  # returns float, defaults to 0.0
```

## Prevention

- `_safe_optional_float()` exists specifically for this case
- Type annotations on both functions make the contract explicit
- If you need None semantics, use the optional variant — never override safe_float's contract
