"""Tests for NaN-safe numeric coercion."""
import math

import pytest

from lib.nan_safety import safe_int, safe_float, sanitize_nan_in_dict


class TestSafeInt:
    def test_returns_int_for_int(self):
        assert safe_int(5) == 5

    def test_returns_int_for_float(self):
        assert safe_int(5.7) == 5

    def test_returns_zero_for_none(self):
        assert safe_int(None) == 0

    def test_returns_zero_for_nan(self):
        assert safe_int(float("nan")) == 0

    def test_returns_zero_for_inf(self):
        assert safe_int(float("inf")) == 0

    def test_default_override(self):
        assert safe_int(None, default=-1) == -1

    def test_returns_int_for_string_number(self):
        assert safe_int("42") == 42

    def test_returns_default_for_garbage_string(self):
        assert safe_int("hello", default=0) == 0


class TestSafeFloat:
    def test_returns_float_for_float(self):
        assert safe_float(5.5) == 5.5

    def test_returns_float_for_int(self):
        assert safe_float(5) == 5.0

    def test_returns_default_for_nan(self):
        assert safe_float(float("nan")) == 0.0

    def test_returns_default_for_inf(self):
        assert safe_float(float("inf")) == 0.0

    def test_returns_default_for_none(self):
        assert safe_float(None) == 0.0


class TestSanitizeNanInDict:
    def test_strips_nan_from_dict(self):
        result = sanitize_nan_in_dict({"a": 1, "b": float("nan"), "c": "ok"})
        assert result == {"a": 1, "b": None, "c": "ok"}

    def test_handles_nested_dict(self):
        result = sanitize_nan_in_dict(
            {"outer": {"inner": float("nan"), "ok": 5}}
        )
        assert result == {"outer": {"inner": None, "ok": 5}}

    def test_handles_list_of_dicts(self):
        result = sanitize_nan_in_dict(
            {"rows": [{"x": float("nan")}, {"x": 1}]}
        )
        assert result == {"rows": [{"x": None}, {"x": 1}]}
