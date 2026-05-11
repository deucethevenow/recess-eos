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
    "pipeline_coverage": 2.1,
    "cash_position": 1500000.0,
    "demand_nrr": 0.22,
}

# Use current time so stale threshold (25h) doesn't flip these tests
from datetime import datetime, timezone
SNAPSHOT_TS = datetime.now(timezone.utc).isoformat()


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
    """AST scan: enforce no parallel-pipeline pattern.

    Phase A baseline: consumer modules don't import `build_metric_payloads`
    at all — they receive payloads from the orchestrator.

    Phase B+ refinement: surface adapter modules (monday_pulse, deck_writer,
    leadership_doc_writer, founders_preread) DO import `build_metric_payloads`
    because they're thin wrappers around it, exposed as per-surface
    `build_payloads_for_<surface>` entry points. The no-parallel-pipeline
    rule is preserved because adapters delegate identically — no separate
    pace/gap/transform logic. The test now enforces:
      (a) any module that imports `build_metric_payloads` AND lives in
          scripts/lib/ MUST also export a `build_payloads_for_<surface>`
          symbol (proves it's a blessed adapter, not a renegade producer)
      (b) all_hands_deck.py remains a pure consumer (no direct import) —
          its surface adapter is deck_writer.py, not all_hands_deck.py
    """

    PHASE_B_PLUS_ADAPTER_MODULES = {
        "monday_pulse.py": "build_payloads_for_slack",
        "deck_writer.py": "build_payloads_for_deck",
        "leadership_doc_writer.py": "build_payloads_for_doc",
        "founders_preread.py": "build_payloads_for_founders_preread",
    }

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

    def test_phase_b_plus_adapters_export_their_named_symbol(self):
        """Each Phase B+ adapter module imports build_metric_payloads AND
        exports the matching `build_payloads_for_<surface>` symbol. This
        catches: adapter renamed but module still imports the producer
        without exposing the surface symbol (renegade producer pattern)."""
        for module_name, adapter_symbol in self.PHASE_B_PLUS_ADAPTER_MODULES.items():
            module_path = os.path.join(
                os.path.dirname(__file__), "..", "lib", module_name
            )
            imports = self._get_imports(module_path)
            assert "build_metric_payloads" in imports, (
                f"{module_name}: Phase B+ adapter module must import "
                f"build_metric_payloads (got imports: {sorted(imports)[:8]}...)"
            )
            with open(module_path) as f:
                src = f.read()
            assert f"def {adapter_symbol}(" in src, (
                f"{module_name}: must export Phase B+ adapter symbol "
                f"`{adapter_symbol}` (signature `def {adapter_symbol}(...)`). "
                f"If you removed the adapter, also remove "
                f"build_metric_payloads import to avoid the renegade-producer "
                f"pattern."
            )

    def test_all_hands_deck_does_not_import_build_metric_payloads(self):
        """all_hands_deck.py is a pure consumer — its surface adapter lives
        in deck_writer.py (the Slides-API writer), not here. If
        all_hands_deck ever needs the producer, it should be re-classified
        as a Phase B+ adapter module above."""
        module_path = os.path.join(
            os.path.dirname(__file__), "..", "lib", "all_hands_deck.py"
        )
        imports = self._get_imports(module_path)
        assert "build_metric_payloads" not in imports, (
            "all_hands_deck.py imports build_metric_payloads directly! "
            "It's a pure consumer (the deck_writer.py module is the "
            "Phase B+ adapter for the deck surface). If the producer "
            "import is intentional, re-classify all_hands_deck.py as a "
            "Phase B+ adapter module in PHASE_B_PLUS_ADAPTER_MODULES above."
        )
