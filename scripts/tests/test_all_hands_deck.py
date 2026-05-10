"""Tests for the All-Hands Deck Slides consumer."""

import sys
import os
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from lib.all_hands_deck import (
    DECK_ID,
    DEPT_SLIDE_MAP,
    DeckStructureDriftError,
    SlideReplacement,
    apply_deck_updates,
    extract_goal_progress_text,
    render_deck_updates,
)
from lib.metric_payloads import MetricPayload
from lib.orchestrator import ConsumerResult


# ── Fixtures ──────────────────────────────────────────────────────────


def _payload(**overrides) -> MetricPayload:
    """Create a MetricPayload with sensible defaults.

    Mirrors production: target_display is auto-populated from target+format_spec
    via _compute_target_display, exactly like build_metric_payloads does. Tests
    that need a custom target_display can pass it explicitly via overrides.
    """
    from lib.metric_payloads import _compute_target_display
    defaults = dict(
        metric_name="Pipeline Coverage",
        config_key="Pipeline Coverage",
        registry_key="Pipeline Coverage",
        snapshot_column="pipeline_coverage",
        raw_value=2.1,
        transformed_value=0.84,
        target=2.5,
        display_value="2.1x",
        metric_unit="multiplier",
        format_spec="multiplier",
        transform="percent_higher_is_better",
        snapshot_timestamp="2026-04-14T08:00:00Z",
        sensitivity="public",
        availability_state="live",
        dept_id="sales",
        notes=None,
    )
    defaults.update(overrides)
    if "target_display" not in defaults:
        defaults["target_display"] = _compute_target_display(
            defaults.get("target"), defaults.get("format_spec", "")
        )
    return MetricPayload(**defaults)


# ── extract_goal_progress_text ────────────────────────────────────────


class TestExtractGoalProgressText:

    def test_metric_without_target(self):
        p = _payload(display_value="$1.2M", target=None)
        assert extract_goal_progress_text(p) == "$1.2M"

    def test_metric_with_target(self):
        p = _payload(display_value="2.1x", target=2.5, format_spec="multiplier")
        result = extract_goal_progress_text(p)
        assert "2.1x" in result
        assert "2.5x" in result

    def test_stale_metric_has_stale_badge(self):
        p = _payload(display_value="2.1x", availability_state="stale")
        result = extract_goal_progress_text(p)
        assert "[stale]" in result

    def test_null_metric_shows_dash(self):
        p = _payload(display_value="\u2014", availability_state="null", target=None)
        result = extract_goal_progress_text(p)
        assert "\u2014" in result


# ── render_deck_updates ───────────────────────────────��───────────────


class TestRenderDeckUpdates:

    def test_produces_replacements_for_automated_metrics(self):
        payloads = {"sales": [_payload()]}

        replacements, results = render_deck_updates(payloads, "2026-04-14T08:00:00Z")

        assert len(replacements) >= 1
        assert all(isinstance(r, SlideReplacement) for r in replacements)
        # The replacement should contain the display value
        assert any("2.1x" in r.replacement for r in replacements)

    def test_skips_needs_build_metrics(self):
        payloads = {
            "sales": [_payload(
                metric_name="Win Rate",
                registry_key="Win Rate",
                availability_state="needs_build",
                display_value="\U0001f528 Needs Build",
            )],
        }

        replacements, results = render_deck_updates(payloads, "2026-04-14T08:00:00Z")

        # needs_build metrics should still produce a replacement (with the badge text)
        # but the ConsumerResult should reflect "delivered"
        assert len(results) == 1

    def test_excludes_founders_only_metrics(self):
        payloads = {
            "sales": [
                _payload(metric_name="Public", registry_key="Public", sensitivity="public"),
                _payload(metric_name="Secret", registry_key="Secret", sensitivity="founders_only"),
            ],
        }

        replacements, results = render_deck_updates(payloads, "2026-04-14T08:00:00Z")

        # Only public + leadership metrics should produce replacements
        replacement_names = {r.metric_name for r in replacements}
        assert "Public" in replacement_names
        assert "Secret" not in replacement_names

        # But we should have ConsumerResults for both
        result_keys = {r.registry_key for r in results}
        assert "Secret" in result_keys
        secret_result = [r for r in results if r.registry_key == "Secret"][0]
        assert secret_result.action == "skipped"

    def test_placeholder_format_is_correct(self):
        """Placeholder should be {{dept_id_metric_key_snake_case}}."""
        payloads = {"sales": [_payload(registry_key="Pipeline Coverage")]}

        replacements, results = render_deck_updates(payloads, "2026-04-14T08:00:00Z")

        assert len(replacements) >= 1
        assert replacements[0].placeholder == "{{sales_pipeline_coverage}}"

    def test_returns_consumer_result_per_metric(self):
        payloads = {
            "sales": [
                _payload(registry_key="M1", metric_name="M1"),
                _payload(registry_key="M2", metric_name="M2"),
            ],
        }

        replacements, results = render_deck_updates(payloads, "2026-04-14T08:00:00Z")

        assert len(results) == 2
        assert all(r.consumer == "slides_deck" for r in results)

    def test_empty_payloads_returns_empty_list(self):
        replacements, results = render_deck_updates({}, "2026-04-14T08:00:00Z")

        assert replacements == []
        assert results == []


# ── apply_deck_updates ────────────────────────────────────────────────


class TestApplyDeckUpdates:

    def test_dry_run_returns_dry_run_results(self):
        replacements = [
            SlideReplacement(
                placeholder="{{sales_pipeline_coverage}}",
                replacement="2.1x / 2.5x",
                dept_id="sales",
                metric_name="Pipeline Coverage",
                registry_key="Pipeline Coverage",
            ),
        ]

        results = apply_deck_updates(replacements, dry_run=True)

        assert len(results) == 1
        assert results[0].action == "dry_run"

    def test_missing_placeholder_raises_drift_error(self):
        """When deck content doesn't contain expected placeholders, raise."""
        replacements = [
            SlideReplacement(
                placeholder="{{sales_nonexistent_metric}}",
                replacement="42",
                dept_id="sales",
                metric_name="Nonexistent",
                registry_key="Nonexistent",
            ),
        ]

        # When not dry_run, apply_deck_updates needs to check the deck.
        # We mock the MCP call to return slide content without the placeholder.
        with patch("lib.all_hands_deck._get_slide_content") as mock_get:
            mock_get.return_value = "Some slide text without the expected placeholder"

            with pytest.raises(DeckStructureDriftError):
                apply_deck_updates(replacements, dry_run=False)
