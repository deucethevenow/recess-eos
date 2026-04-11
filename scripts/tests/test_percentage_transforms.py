"""Tests for percentage transforms — converting raw BQ values to Asana Goal 0.0-1.0 scale.

CRITICAL: Asana Goals with metric_unit="percentage" expect 0.0-1.0.
Pushing "45" to a percentage Goal shows "4500%". These transforms prevent that.
"""
import pytest
from lib.percentage_transforms import apply_transform


class TestRawTransform:
    def test_returns_value_unchanged(self):
        assert apply_transform(42.5, "raw") == 42.5

    def test_returns_none_unchanged(self):
        """raw transform on None should return None."""
        assert apply_transform(None, "raw") is None


class TestPercentHigherIsBetter:
    def test_nrr_halfway_to_target(self):
        """NRR 25% toward target 50% → 0.50"""
        result = apply_transform(0.25, "percent_higher_is_better", target=0.50)
        assert result == 0.5

    def test_at_target(self):
        """At target → 1.0"""
        result = apply_transform(0.50, "percent_higher_is_better", target=0.50)
        assert result == 1.0

    def test_exceeds_target_capped(self):
        """Above target → capped at 1.0"""
        result = apply_transform(0.75, "percent_higher_is_better", target=0.50)
        assert result == 1.0

    def test_zero_value(self):
        """Zero value → 0.0"""
        result = apply_transform(0.0, "percent_higher_is_better", target=0.50)
        assert result == 0.0

    def test_no_target_returns_none(self):
        """No target → None (can't compute percentage)"""
        result = apply_transform(0.25, "percent_higher_is_better", target=None)
        assert result is None

    def test_zero_target_returns_none(self):
        """Zero target → None (division by zero guard)"""
        result = apply_transform(0.25, "percent_higher_is_better", target=0)
        assert result is None

    def test_negative_value_clamped(self):
        """Negative raw value → clamped to 0.0"""
        result = apply_transform(-5.0, "percent_higher_is_better", target=10.0)
        assert result == 0.0

    def test_pipeline_coverage_example(self):
        """Pipeline coverage 2.1x toward 2.5x target → 0.84"""
        result = apply_transform(2.1, "percent_higher_is_better", target=2.5)
        assert abs(result - 0.84) < 0.01


class TestPercentLowerIsBetter:
    def test_fulfillment_halfway(self):
        """Fulfillment 45 days, baseline 60, target 30 → 0.5"""
        result = apply_transform(45.0, "percent_lower_is_better", target=30.0, baseline=60.0)
        assert result == 0.5

    def test_at_target(self):
        """At target → 1.0"""
        result = apply_transform(30.0, "percent_lower_is_better", target=30.0, baseline=60.0)
        assert result == 1.0

    def test_better_than_target_capped(self):
        """Better than target → capped at 1.0"""
        result = apply_transform(20.0, "percent_lower_is_better", target=30.0, baseline=60.0)
        assert result == 1.0

    def test_at_baseline(self):
        """At baseline (no improvement) → 0.0"""
        result = apply_transform(60.0, "percent_lower_is_better", target=30.0, baseline=60.0)
        assert result == 0.0

    def test_worse_than_baseline_clamped(self):
        """Worse than baseline → clamped to 0.0"""
        result = apply_transform(80.0, "percent_lower_is_better", target=30.0, baseline=60.0)
        assert result == 0.0

    def test_no_baseline_returns_none(self):
        """No baseline → None"""
        result = apply_transform(45.0, "percent_lower_is_better", target=30.0, baseline=None)
        assert result is None

    def test_no_target_returns_none(self):
        """No target → None"""
        result = apply_transform(45.0, "percent_lower_is_better", target=None, baseline=60.0)
        assert result is None

    def test_baseline_equals_target_returns_none(self):
        """baseline == target → None (division by zero)"""
        result = apply_transform(45.0, "percent_lower_is_better", target=30.0, baseline=30.0)
        assert result is None


class TestUnknownTransform:
    def test_returns_none(self):
        result = apply_transform(42.0, "not_a_real_transform")
        assert result is None
