"""NaN-safe numeric coercion.

Pandas .to_dataframe() converts SQL NULL → float('nan') which is truthy.
Patterns like `val or 0` produce nan, which crashes int() with ValueError.
Always use safe_int / safe_float at numeric boundaries when reading BQ data.
"""
import math
from typing import Any


def _is_bad_number(value: Any) -> bool:
    """Returns True for None, nan, inf, or -inf."""
    if value is None:
        return True
    try:
        f = float(value)
    except (TypeError, ValueError):
        return True
    return math.isnan(f) or math.isinf(f)


def safe_int(value: Any, default: int = 0) -> int:
    """Return int(value), or default if value is None/nan/inf/non-numeric."""
    if _is_bad_number(value):
        return default
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def safe_float(value: Any, default: float = 0.0) -> float:
    """Return float(value), or default if value is None/nan/inf/non-numeric."""
    if _is_bad_number(value):
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def sanitize_nan_in_dict(data: Any) -> Any:
    """Recursively replace nan/inf with None in a dict/list structure."""
    if isinstance(data, dict):
        return {k: sanitize_nan_in_dict(v) for k, v in data.items()}
    if isinstance(data, list):
        return [sanitize_nan_in_dict(v) for v in data]
    if isinstance(data, float) and (math.isnan(data) or math.isinf(data)):
        return None
    return data
