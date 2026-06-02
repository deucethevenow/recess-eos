"""Path 1 integration test — All Hands Deck Updater (Task 7).

Validates the end-to-end shape from MetricPayload → SlideReplacement → MCP-ready
text replacements. Locks in the contract that production wiring (Path 2) will
need to match.

This is a STRUCTURAL test — it asserts exact placeholder names + replacement
text format, so any future change that breaks the contract fails loudly. It
does NOT call the Slides MCP (lib stays MCP-agnostic) but it captures the
exact replacement strings the MCP adapter will receive.

Live validation evidence (this exact payload set was applied to a real test
deck on 2026-04-26 and verified round-trip):
    https://docs.google.com/presentation/d/1qntN3ya_elLPJtWN4cipxO-bZZfgrZS4Zhsdeax_DNE
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

from lib.all_hands_deck import render_deck_updates, render_rock_updates
from lib.metric_payloads import MetricPayload


# Re-use the validation script's payload builder so test + script stay in sync.
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_VALIDATE_SCRIPT = _REPO_ROOT / "scripts" / "validate_path1_deck_updater.py"


def _load_payload_builder():
    """Import build_test_payloads() from the validation script."""
    spec = importlib.util.spec_from_file_location(
        "validate_path1_deck_updater", _VALIDATE_SCRIPT
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules["validate_path1_deck_updater"] = mod
    spec.loader.exec_module(mod)
    return mod.build_test_payloads


@pytest.fixture
def test_payloads() -> dict[str, list[MetricPayload]]:
    return _load_payload_builder()()


# ─── Render contract ────────────────────────────────────────────────────


class TestPath1IntegrationContract:
    """Locks in the exact placeholder + replacement format the deck expects."""

    def test_renders_exactly_five_public_replacements(self, test_payloads):
        """7 input payloads (5 public + 2 founders_only) → 5 SlideReplacements."""
        replacements, _ = render_deck_updates(test_payloads, "2026-04-26T18:00:00Z")
        assert len(replacements) == 5

    def test_no_founders_only_replacements_leak(self, test_payloads):
        """Sensitivity filter MUST drop founders_only metrics from public render."""
        replacements, _ = render_deck_updates(test_payloads, "2026-04-26T18:00:00Z")
        founders_placeholders = {
            "{{founders_bank_cash_available}}",
            "{{founders_conservative_runway}}",
        }
        rendered_placeholders = {r.placeholder for r in replacements}
        leaked = founders_placeholders & rendered_placeholders
        assert leaked == set(), (
            f"Founders-only placeholders leaked into public deck: {leaked}. "
            "This is a sensitivity filter regression — DO NOT relax this test."
        )

    def test_consumer_results_record_skipped_for_founders_metrics(self, test_payloads):
        """skipped ConsumerResults must explain WHY for audit trail."""
        _, results = render_deck_updates(test_payloads, "2026-04-26T18:00:00Z")
        skipped = [r for r in results if r.action == "skipped"]
        assert len(skipped) == 2
        for r in skipped:
            assert r.consumer == "slides_deck"
            assert "founders_only" in (r.error_message or "").lower()

    def test_placeholder_format_snake_case_with_dept_prefix(self, test_payloads):
        """Locks the {{<dept>_<registry_key_snake>}} contract."""
        replacements, _ = render_deck_updates(test_payloads, "2026-04-26T18:00:00Z")
        expected_set = {
            "{{sales_bookings_goal_attainment}}",
            "{{sales_demand_nrr}}",
            "{{sales_pipeline_coverage}}",
            "{{demand_am_nps_score}}",
            "{{demand_am_days_to_fulfill}}",
        }
        assert {r.placeholder for r in replacements} == expected_set

    def test_replacement_text_includes_target_when_present(self, test_payloads):
        """display_value / target — slash-separated."""
        replacements, _ = render_deck_updates(test_payloads, "2026-04-26T18:00:00Z")
        by_ph = {r.placeholder: r.replacement for r in replacements}
        assert by_ph["{{sales_bookings_goal_attainment}}"] == "$2.59M / $10.8M"
        assert by_ph["{{sales_demand_nrr}}"] == "13% / 50.0%"
        assert by_ph["{{sales_pipeline_coverage}}"] == "0.88x / 2.5x"
        assert by_ph["{{demand_am_nps_score}}"] == "79.3 / 75"
        assert by_ph["{{demand_am_days_to_fulfill}}"] == "11 days / 30 days"

    def test_format_specs_round_trip_correctly(self, test_payloads):
        """Each format_spec produces the right target suffix."""
        replacements, _ = render_deck_updates(test_payloads, "2026-04-26T18:00:00Z")
        by_ph = {r.placeholder: r.replacement for r in replacements}
        # currency → "$X.XM"
        assert "$10.8M" in by_ph["{{sales_bookings_goal_attainment}}"]
        # percent → "X.X%"
        assert "50.0%" in by_ph["{{sales_demand_nrr}}"]
        # multiplier → "X.Xx"
        assert "2.5x" in by_ph["{{sales_pipeline_coverage}}"]
        # number/count → integer with no suffix
        assert "/ 75" in by_ph["{{demand_am_nps_score}}"]
        # days → "X days"
        assert "30 days" in by_ph["{{demand_am_days_to_fulfill}}"]

    def test_consumer_field_set_to_slides_deck(self, test_payloads):
        """All ConsumerResults must be tagged consumer='slides_deck'."""
        _, results = render_deck_updates(test_payloads, "2026-04-26T18:00:00Z")
        consumers = {r.consumer for r in results}
        assert consumers == {"slides_deck"}


# ─── Rock contract ──────────────────────────────────────────────────────


@pytest.fixture
def test_rocks() -> dict[str, list[dict]]:
    """Mock rock data matching what's live in the test deck."""
    return {
        "sales": [
            {"name": "Q2 NRR via ABM", "owner_name": "Andy Cooper",
             "completion_percent": 70.0, "status": "active",
             "asana_project_id": "p_sales_1"},
            {"name": "Walmart BTC Launch", "owner_name": "Andy Cooper",
             "completion_percent": 50.0, "status": "active",
             "asana_project_id": "p_sales_2"},
        ],
        "demand_am": [
            {"name": "Onboard New ProServ Vendors", "owner_name": "Claire A",
             "completion_percent": 0.0, "status": "active",
             "asana_project_id": "p_am_1"},
        ],
        "engineering": [],  # empty — should be filtered
        "supply": [
            {"name": "Archived rock", "owner_name": "X", "completion_percent": 100,
             "status": "archived", "asana_project_id": "p_old_1"},  # archived
        ],
    }


class TestRockUpdatesContract:
    """Locks in the {{rocks_<dept_id>}} contract for all-hands deck rocks."""

    def test_renders_only_depts_with_active_rocks(self, test_rocks):
        """4 input depts (sales=2 active, demand_am=1, engineering=0, supply=1 archived)
        → 2 SlideReplacements (sales, demand_am)."""
        replacements, _ = render_rock_updates(test_rocks, "2026-04-26T18:00:00Z")
        assert len(replacements) == 2
        assert {r.dept_id for r in replacements} == {"sales", "demand_am"}

    def test_archived_rocks_are_filtered(self, test_rocks):
        """Rocks with status='archived' must not appear in any replacement."""
        replacements, results = render_rock_updates(test_rocks, "2026-04-26T18:00:00Z")
        for r in replacements:
            assert "Archived rock" not in r.replacement
        # No ConsumerResult delivered for the archived rock either
        delivered_keys = {r.registry_key for r in results if r.action == "delivered"}
        assert "p_old_1" not in delivered_keys

    def test_placeholder_format(self, test_rocks):
        """Locks the {{rocks_<dept_id>}} contract."""
        replacements, _ = render_rock_updates(test_rocks, "2026-04-26T18:00:00Z")
        placeholders = {r.placeholder for r in replacements}
        assert placeholders == {"{{rocks_sales}}", "{{rocks_demand_am}}"}

    def test_color_emoji_thresholds(self):
        """Locks 🟢 ≥66 / 🟡 33-65 / 🔴 <33 thresholds (match Monday Pulse)."""
        rocks = {
            "test": [
                {"name": "Green", "owner_name": "X", "completion_percent": 80,
                 "status": "active", "asana_project_id": "g"},
                {"name": "Yellow", "owner_name": "X", "completion_percent": 50,
                 "status": "active", "asana_project_id": "y"},
                {"name": "Red", "owner_name": "X", "completion_percent": 10,
                 "status": "active", "asana_project_id": "r"},
                {"name": "Edge66", "owner_name": "X", "completion_percent": 66,
                 "status": "active", "asana_project_id": "e66"},  # boundary: 66 = green
                {"name": "Edge33", "owner_name": "X", "completion_percent": 33,
                 "status": "active", "asana_project_id": "e33"},  # boundary: 33 = yellow
            ],
        }
        replacements, _ = render_rock_updates(rocks, "2026-04-26T18:00:00Z")
        text = replacements[0].replacement
        assert "\U0001F7E2 Green" in text  # 80 → green
        assert "\U0001F7E1 Yellow" in text  # 50 → yellow
        assert "\U0001F534 Red" in text     # 10 → red
        assert "\U0001F7E2 Edge66" in text  # 66 → green (boundary)
        assert "\U0001F7E1 Edge33" in text  # 33 → yellow (boundary)

    def test_replacement_includes_owner_in_parens(self, test_rocks):
        """Locks the '<icon> <name> — <pct>% (<owner>)' format."""
        replacements, _ = render_rock_updates(test_rocks, "2026-04-26T18:00:00Z")
        sales = next(r for r in replacements if r.dept_id == "sales")
        assert "Q2 NRR via ABM — 70% (Andy Cooper)" in sales.replacement
        assert "Walmart BTC Launch — 50% (Andy Cooper)" in sales.replacement

    def test_consumer_field_distinguishes_rocks_from_metrics(self, test_rocks):
        """ConsumerResult.consumer must be 'slides_deck_rocks' for audit."""
        _, results = render_rock_updates(test_rocks, "2026-04-26T18:00:00Z")
        assert {r.consumer for r in results} == {"slides_deck_rocks"}

    def test_empty_input_returns_empty_lists(self):
        """No rocks at all → no replacements, no results."""
        replacements, results = render_rock_updates({}, "2026-04-26T18:00:00Z")
        assert replacements == []
        assert results == []

    def test_missing_owner_renders_unassigned(self):
        """Defensive: rock with missing owner_name shows 'Unassigned'."""
        rocks = {"sales": [{"name": "Orphan", "owner_name": None,
                            "completion_percent": 50, "status": "active",
                            "asana_project_id": "o1"}]}
        replacements, _ = render_rock_updates(rocks, "2026-04-26T18:00:00Z")
        assert "(Unassigned)" in replacements[0].replacement

    def test_handles_non_numeric_completion_percent(self):
        """Defensive: garbage completion_percent doesn't raise."""
        rocks = {"sales": [{"name": "Bad", "owner_name": "X",
                            "completion_percent": "not a number", "status": "active",
                            "asana_project_id": "b1"}]}
        replacements, _ = render_rock_updates(rocks, "2026-04-26T18:00:00Z")
        # Non-numeric → 0% → red
        assert "\U0001F534 Bad — 0% (X)" in replacements[0].replacement


# ─── Live deck reference (documentation, not assertion) ─────────────────

LIVE_TEST_DECK_ID = "1qntN3ya_elLPJtWN4cipxO-bZZfgrZS4Zhsdeax_DNE"


def test_live_deck_id_documented():
    """Sanity test that the live deck ID is captured for traceability.

    On 2026-04-26 the replacements rendered above were applied to this deck via
    mcp__google-drive__replaceAllTextInSlides and round-trip verified. The deck
    serves as the canonical Path 1 evidence artifact.
    """
    assert LIVE_TEST_DECK_ID == "1qntN3ya_elLPJtWN4cipxO-bZZfgrZS4Zhsdeax_DNE"
