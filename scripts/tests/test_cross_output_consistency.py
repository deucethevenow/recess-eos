"""Cross-Output Consistency Tests — THE single-truth gate.

Verifies that all consumers see identical data from the same MetricPayload.
Every test config uses ONLY allowed fields + MOCK_REGISTRY injection.
No forbidden config fields (transform, format, etc.) appear here.
"""

import ast
import os
import sys
from dataclasses import FrozenInstanceError

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from lib.metric_payloads import MetricPayload, build_metric_payloads
from lib.monday_pulse import extract_metric_display_value
from lib.all_hands_deck import extract_goal_progress_text


# ── Mock registry (mirrors real structure, no forbidden fields in configs) ─────

MOCK_REGISTRY = {
    "Pipeline Coverage": {
        "bq_key": "pipeline_coverage",
        "format": "multiplier",
        "higher_is_better": True,
    },
    "Bank Cash (Available)": {
        "bq_key": "cash_position",
        "format": "currency",
        "higher_is_better": True,
    },
    "Demand NRR": {
        "bq_key": "demand_nrr",
        "format": "percent",
        "higher_is_better": True,
    },
}


def _make_meeting_config(metrics):
    """Config with ONLY allowed fields — no forbidden logic fields."""
    return {
        "id": "sales",
        "name": "Sales L10",
        "scorecard_metrics": metrics,
    }


def _metric_config(name, registry_key, target=None, sensitivity="public",
                    status="automated", null_behavior="show_dash"):
    """Metric config with ONLY pointer fields. No transform, format, etc."""
    return {
        "name": name,
        "registry_key": registry_key,
        "target": target,
        "sensitivity": sensitivity,
        "status": status,
        "null_behavior": null_behavior,
    }


SNAPSHOT_ROW = {
    "snapshot_timestamp": "2026-04-14T08:00:00Z",
    "pipeline_coverage": 2.1,
    "cash_position": 1500000.0,
    "demand_nrr": 0.22,
}

SNAPSHOT_TS = "2026-04-14T08:00:00Z"


# ── Same metric across all surfaces ──────────────────────────────────


class TestSameMetricAcrossAllSurfaces:

    def test_pipeline_coverage_consistent(self):
        """Pipeline Coverage displays the same value in Slack and Slides."""
        meeting = _make_meeting_config([
            _metric_config("Pipeline Coverage", "Pipeline Coverage", target=2.5),
        ])
        payloads = build_metric_payloads(meeting, SNAPSHOT_ROW, SNAPSHOT_TS, registry=MOCK_REGISTRY)

        assert len(payloads) == 1
        p = payloads[0]

        # The display value is the canonical source
        assert p.display_value == "2.1x"

        # Slack consumer extracts the same value (live → no badge)
        slack_value = extract_metric_display_value(p)
        assert slack_value == "2.1x"

        # Slides consumer includes the value in its progress text
        slides_text = extract_goal_progress_text(p)
        assert "2.1x" in slides_text

    def test_nrr_consistent(self):
        """Demand NRR percent format is consistent across consumers."""
        meeting = _make_meeting_config([
            _metric_config("Demand NRR", "Demand NRR", target=0.50),
        ])
        payloads = build_metric_payloads(meeting, SNAPSHOT_ROW, SNAPSHOT_TS, registry=MOCK_REGISTRY)

        assert len(payloads) == 1
        p = payloads[0]

        assert p.display_value == "22.0%"

        slack_value = extract_metric_display_value(p)
        assert slack_value == "22.0%"

        slides_text = extract_goal_progress_text(p)
        assert "22.0%" in slides_text


# ── Sensitivity exclusion ─────────────────────────────────────────────


class TestSensitivityExclusion:

    def test_founders_metric_excluded_from_public_filter(self):
        """A founders_only metric should not pass a public sensitivity filter."""
        from lib.metric_payloads import filter_by_sensitivity

        meeting = _make_meeting_config([
            _metric_config("Bank Cash (Available)", "Bank Cash (Available)",
                           sensitivity="founders_only"),
        ])
        payloads = build_metric_payloads(meeting, SNAPSHOT_ROW, SNAPSHOT_TS, registry=MOCK_REGISTRY)

        public_only = filter_by_sensitivity(payloads, "public")
        assert len(public_only) == 0

    def test_leadership_metric_included_in_leadership_filter(self):
        """A leadership metric should pass a leadership sensitivity filter."""
        from lib.metric_payloads import filter_by_sensitivity

        meeting = _make_meeting_config([
            _metric_config("Pipeline Coverage", "Pipeline Coverage",
                           sensitivity="leadership"),
        ])
        payloads = build_metric_payloads(meeting, SNAPSHOT_ROW, SNAPSHOT_TS, registry=MOCK_REGISTRY)

        leadership = filter_by_sensitivity(payloads, "leadership")
        assert len(leadership) == 1


# ── Stale propagation ─────────────────────────────────────────────────


class TestStalePropagation:

    def test_stale_timestamp_marks_all_payloads_stale(self):
        """An old snapshot_timestamp should make all payloads stale."""
        meeting = _make_meeting_config([
            _metric_config("Pipeline Coverage", "Pipeline Coverage"),
            _metric_config("Demand NRR", "Demand NRR"),
        ])
        old_ts = "2020-01-01T00:00:00Z"  # definitely stale
        payloads = build_metric_payloads(meeting, SNAPSHOT_ROW, old_ts, registry=MOCK_REGISTRY)

        # All should be stale (or null, but these have values)
        for p in payloads:
            assert p.availability_state == "stale", (
                f"{p.metric_name} should be stale with timestamp {old_ts}, "
                f"got {p.availability_state}"
            )


# ── Payload immutability ──────────────────────────────────────────────


class TestPayloadImmutability:

    def test_consumer_cannot_mutate_payload(self):
        """MetricPayload is a frozen dataclass — mutation raises."""
        meeting = _make_meeting_config([
            _metric_config("Pipeline Coverage", "Pipeline Coverage"),
        ])
        payloads = build_metric_payloads(meeting, SNAPSHOT_ROW, SNAPSHOT_TS, registry=MOCK_REGISTRY)
        p = payloads[0]

        with pytest.raises(FrozenInstanceError):
            p.display_value = "HACKED"


# ── No consumer bypasses orchestrator ─────────────────────────────────


class TestNoConsumerBypassesOrchestrator:
    """AST scan: consumers must NOT import build_metric_payloads directly."""

    def _get_imports(self, module_path: str) -> set[str]:
        """Parse a Python file and return all imported names."""
        with open(module_path) as f:
            tree = ast.parse(f.read())

        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    imported.add(alias.name)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    imported.add(alias.name)
        return imported

    def test_monday_pulse_does_not_import_build_metric_payloads(self):
        module_path = os.path.join(
            os.path.dirname(__file__), "..", "lib", "monday_pulse.py"
        )
        imports = self._get_imports(module_path)
        assert "build_metric_payloads" not in imports, (
            "monday_pulse.py imports build_metric_payloads directly! "
            "Consumers must receive payloads from the orchestrator."
        )

    def test_all_hands_deck_does_not_import_build_metric_payloads(self):
        module_path = os.path.join(
            os.path.dirname(__file__), "..", "lib", "all_hands_deck.py"
        )
        imports = self._get_imports(module_path)
        assert "build_metric_payloads" not in imports, (
            "all_hands_deck.py imports build_metric_payloads directly! "
            "Consumers must receive payloads from the orchestrator."
        )
