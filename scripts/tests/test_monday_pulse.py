"""Tests for the Monday Pulse Slack consumer."""

import sys
import os
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from lib.monday_pulse import (
    extract_metric_display_value,
    render_monday_pulse,
    post_monday_pulse,
    SlackPostError,
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
        metric_name="Demand NRR",
        config_key="Demand NRR",
        registry_key="Demand NRR",
        snapshot_column="demand_nrr",
        raw_value=0.22,
        transformed_value=0.44,
        target=0.50,
        display_value="22.0%",
        metric_unit="percent",
        format_spec="percent",
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


def _meeting_config(meeting_id="sales", name="Sales L10"):
    return {"id": meeting_id, "name": name, "scorecard_metrics": []}


# ── extract_metric_display_value ──────────────────────────────────────


class TestExtractMetricDisplayValue:

    def test_returns_display_value_for_live_metric(self):
        p = _payload(display_value="22.0%", availability_state="live")
        assert extract_metric_display_value(p) == "22.0%"

    def test_appends_stale_badge(self):
        p = _payload(display_value="22.0%", availability_state="stale")
        result = extract_metric_display_value(p)
        assert "[stale]" in result
        assert result == "22.0% [stale]"

    def test_returns_display_value_for_null(self):
        p = _payload(display_value="\u2014", availability_state="null")
        assert extract_metric_display_value(p) == "\u2014"

    def test_returns_display_value_for_needs_build(self):
        p = _payload(display_value="\U0001f528 Needs Build", availability_state="needs_build")
        result = extract_metric_display_value(p)
        assert result == "\U0001f528 Needs Build"


# ── render_monday_pulse ───────────────────────────────────────────────


class TestRenderMondayPulse:

    def test_renders_blocks_for_single_dept(self):
        payloads = {"sales": [_payload()]}
        meetings = [_meeting_config("sales", "Sales L10")]

        blocks, results = render_monday_pulse(payloads, "2026-04-14T08:00:00Z", meetings)

        # Should have: header + at least one section + footer
        assert len(blocks) >= 3
        # Find a section with the metric text
        text_blocks = [b for b in blocks if b.get("type") == "section"]
        all_text = " ".join(
            b.get("text", {}).get("text", "") for b in text_blocks
        )
        assert "Sales L10" in all_text
        assert "22.0%" in all_text

    def test_renders_blocks_for_multiple_depts(self):
        payloads = {
            "sales": [_payload(dept_id="sales")],
            "supply": [_payload(
                metric_name="Total Sellable Inventory",
                registry_key="Total Sellable Inventory",
                display_value="1.2M",
                dept_id="supply",
                sensitivity="public",
            )],
        }
        meetings = [
            _meeting_config("sales", "Sales L10"),
            _meeting_config("supply", "Supply L10"),
        ]

        blocks, results = render_monday_pulse(payloads, "2026-04-14T08:00:00Z", meetings)

        all_text = " ".join(
            b.get("text", {}).get("text", "")
            for b in blocks if b.get("type") == "section"
        )
        assert "Sales L10" in all_text
        assert "Supply L10" in all_text

    def test_excludes_founders_only_metrics(self):
        payloads = {
            "sales": [
                _payload(metric_name="Public Metric", sensitivity="public", display_value="100"),
                _payload(metric_name="Secret Metric", sensitivity="founders_only", display_value="999"),
            ],
        }
        meetings = [_meeting_config("sales", "Sales L10")]

        blocks, results = render_monday_pulse(payloads, "2026-04-14T08:00:00Z", meetings)

        all_text = " ".join(
            b.get("text", {}).get("text", "")
            for b in blocks if b.get("type") == "section"
        )
        assert "Public Metric" in all_text
        assert "Secret Metric" not in all_text

    def test_includes_needs_build_with_badge(self):
        payloads = {
            "sales": [_payload(
                metric_name="Win Rate",
                display_value="\U0001f528 Needs Build",
                availability_state="needs_build",
            )],
        }
        meetings = [_meeting_config("sales", "Sales L10")]

        blocks, results = render_monday_pulse(payloads, "2026-04-14T08:00:00Z", meetings)

        all_text = " ".join(
            b.get("text", {}).get("text", "")
            for b in blocks if b.get("type") == "section"
        )
        assert "Needs Build" in all_text

    def test_stale_metrics_have_stale_suffix(self):
        payloads = {
            "sales": [_payload(display_value="22.0%", availability_state="stale")],
        }
        meetings = [_meeting_config("sales", "Sales L10")]

        blocks, results = render_monday_pulse(payloads, "2026-04-14T08:00:00Z", meetings)

        all_text = " ".join(
            b.get("text", {}).get("text", "")
            for b in blocks if b.get("type") == "section"
        )
        assert "[stale]" in all_text

    def test_returns_consumer_result_per_metric(self):
        payloads = {
            "sales": [
                _payload(metric_name="M1", registry_key="M1"),
                _payload(metric_name="M2", registry_key="M2"),
            ],
        }
        meetings = [_meeting_config("sales", "Sales L10")]

        blocks, results = render_monday_pulse(payloads, "2026-04-14T08:00:00Z", meetings)

        assert len(results) == 2
        assert all(isinstance(r, ConsumerResult) for r in results)
        assert all(r.consumer == "slack_pulse" for r in results)
        keys = {r.registry_key for r in results}
        assert keys == {"M1", "M2"}

    def test_empty_payloads_returns_empty_blocks(self):
        blocks, results = render_monday_pulse({}, "2026-04-14T08:00:00Z", [])

        # Should still have header + footer at minimum, or just be empty
        assert isinstance(blocks, list)
        assert results == []

    def test_dept_with_only_filtered_metrics_still_in_results(self):
        """A dept where ALL metrics are founders_only should still produce ConsumerResults (skipped)."""
        payloads = {
            "sales": [
                _payload(metric_name="Secret", sensitivity="founders_only", registry_key="Secret"),
            ],
        }
        meetings = [_meeting_config("sales", "Sales L10")]

        blocks, results = render_monday_pulse(payloads, "2026-04-14T08:00:00Z", meetings)

        # Should have a ConsumerResult even for skipped metrics
        assert len(results) == 1
        assert results[0].action == "skipped"


# ── post_monday_pulse ─────────────────────────────────────────────────


class TestPostMondayPulse:

    def test_dry_run_returns_dry_run_string(self):
        result = post_monday_pulse(
            blocks=[{"type": "section", "text": {"type": "mrkdwn", "text": "test"}}],
            channel_id="C123",
            slack_token="xoxb-fake",
            dry_run=True,
        )
        assert result == "dry_run"

    @patch("lib.monday_pulse.WebClient")
    def test_posts_to_correct_channel(self, MockWebClient):
        mock_client = MagicMock()
        mock_client.chat_postMessage.return_value = MagicMock(data={"ts": "1234567890.123456"})
        MockWebClient.return_value = mock_client

        result = post_monday_pulse(
            blocks=[{"type": "section", "text": {"type": "mrkdwn", "text": "test"}}],
            channel_id="C0AQP3WH7AB",
            slack_token="xoxb-test",
            dry_run=False,
        )

        mock_client.chat_postMessage.assert_called_once()
        call_kwargs = mock_client.chat_postMessage.call_args[1]
        assert call_kwargs["channel"] == "C0AQP3WH7AB"
        assert result == "1234567890.123456"
