"""Percentage transforms for converting raw BQ values to Asana Goal 0.0-1.0 scale.

CRITICAL: Asana Goals with metric_unit="percentage" expect 0.0-1.0.
Pushing "45" to a percentage Goal shows "4500%". These transforms prevent that.

Transform types:
  raw                      — return value as-is (for count/currency Goals)
  percent_higher_is_better — min(1.0, current / target)
  percent_lower_is_better  — min(1.0, (baseline - current) / (baseline - target))
"""
from typing import Optional
from .nan_safety import safe_float


def apply_transform(
    raw_value: Optional[float],
    transform: str,
    target: Optional[float] = None,
    baseline: Optional[float] = None,
) -> Optional[float]:
    """Apply a named transform to a raw BQ value.

    Returns a float in [0.0, 1.0] for percentage Goals, or the raw value for "raw" transform.
    Returns None if inputs are insufficient for the requested transform.
    """
    if transform == "raw":
        return raw_value

    if raw_value is None:
        return None

    if transform == "percent_higher_is_better":
        if target is None or target == 0:
            return None
        return min(1.0, max(0.0, safe_float(raw_value) / safe_float(target)))

    if transform == "percent_lower_is_better":
        if baseline is None or target is None or baseline == target:
            return None
        return min(1.0, max(0.0,
            (safe_float(baseline) - safe_float(raw_value)) /
            (safe_float(baseline) - safe_float(target))
        ))

    return None  # unknown transform
