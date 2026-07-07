"""eos writers consume the Metric Routing store — P2.3.

Plan: context/plans/2026-07-06-metric-routing.md Phase 2 items 3-4. The
monday_kpi_update dept loop walks routing rows (store order); each surface
writer filters through the resolver's is_visible; rocks are filtered UPSTREAM
per surface (while asana_project_id is still on the item); metric_contract's
registry loader honors KPI_DASHBOARD_REPO.
"""
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# conftest.py injects scripts/ + the dashboard repo (KPI_DASHBOARD_REPO) paths.
import monday_kpi_update as mku
from lib.rendered_row import RenderedRow


def _row(name, dept, sensitivity="public"):
    return RenderedRow(
        metric_name=name, display_label=name, dept_id=dept, sensitivity=sensitivity,
        actual_raw=1.0, target_raw=None, status_icon="⚪", display=f"{name}-display",
        actual_display=f"{name}-actual", target_display=None, trend_display=None,
        is_phase2_placeholder=False, is_special_override=False,
    )


ROUTING = {
    "metrics": {
        "sales": [
            # Store order reversed vs registry order on purpose.
            {"metric": "Demand NRR", "slack": True, "deck": False, "doc": True, "l10": True},
            {"metric": "Pipeline Coverage", "slack": True, "deck": True, "doc": True, "l10": True},
        ],
        "founders": [
            {"metric": "Revenue YTD", "slack": False, "deck": False, "doc": False, "l10": False},
        ],
    },
    "rocks": {
        "111": {"name": "Slack-only Rock", "slack": True, "deck": False, "doc": False, "l10": False},
        "222": {"name": "Everywhere Rock", "slack": True, "deck": True, "doc": True, "l10": True},
    },
}

REGISTRY = {
    "Demand NRR": {},
    "Pipeline Coverage": {},
    "Revenue YTD": {"scorecard_sensitivity": {"founders": "founders_only"}},
}


class TestPerSurfaceRockBuckets:
    def _rock_data(self):
        return {
            "available": True,
            "rocks": [
                {"name": "Slack-only Rock", "owner_email": "deuce@recess.is",
                 "asana_project_id": "111"},
                {"name": "Everywhere Rock", "owner_email": "deuce@recess.is",
                 "asana_project_id": "222"},
                {"name": "New Unknown Rock", "owner_email": "deuce@recess.is",
                 "asana_project_id": "999"},
            ],
            "projects": [],
        }

    def test_bucket_filters_by_surface_toggle(self):
        slack_b = mku._bucket_rocks_by_dept(self._rock_data(), ROUTING, "slack")
        deck_b = mku._bucket_rocks_by_dept(self._rock_data(), ROUTING, "deck")
        slack_names = [r["name"] for r in slack_b["operations"]["rocks"]]
        deck_names = [r["name"] for r in deck_b["operations"]["rocks"]]
        assert "Slack-only Rock" in slack_names
        assert "Slack-only Rock" not in deck_names      # deck toggle False
        assert "Everywhere Rock" in slack_names and "Everywhere Rock" in deck_names
        assert "New Unknown Rock" in slack_names and "New Unknown Rock" in deck_names  # default ON


class TestWriterFiltersViaResolver:
    def test_deck_filter_uses_is_visible_per_surface(self):
        from lib.deck_writer import _filter_visible_rows
        rows = [_row("Demand NRR", "sales"), _row("Pipeline Coverage", "sales")]
        visible = _filter_visible_rows(rows, "deck", ROUTING, REGISTRY)
        # Demand NRR deck toggle is False -> only Pipeline Coverage survives
        assert [r.metric_name for r in visible] == ["Pipeline Coverage"]

    def test_deck_filter_surface_none_passes_everything(self):
        # Rocks slides: rock rows are NOT metrics — visibility was applied
        # upstream via rock_visible; surface=None must be a pass-through.
        from lib.deck_writer import _filter_visible_rows
        rows = [_row("Q3 Rock: Not A Metric", "sales")]
        assert _filter_visible_rows(rows, None, ROUTING, REGISTRY) == rows

    def test_slack_section_filters_and_keeps_store_order(self):
        blocks = mku.build_dept_section_for_slack(
            "sales",
            [_row("Demand NRR", "sales"), _row("Pipeline Coverage", "sales")],
            {"rocks": [], "projects": []},
            ROUTING,
            REGISTRY,
        )
        text = blocks[0]["text"]["text"]
        assert "Demand NRR" in text and "Pipeline Coverage" in text  # both slack-visible
        assert text.index("Demand NRR") < text.index("Pipeline Coverage")  # store order

    def test_doc_section_filters_via_doc_toggle(self):
        from lib.leadership_doc_writer import _build_section_text
        rendered = {"sales": {"scorecard_rows": [
            _row("Demand NRR", "sales"), _row("Pipeline Coverage", "sales")]}}
        # flip doc toggle off for Pipeline Coverage in a copy
        routing = {
            "metrics": {"sales": [
                {"metric": "Demand NRR", "slack": True, "deck": False, "doc": True, "l10": True},
                {"metric": "Pipeline Coverage", "slack": True, "deck": True, "doc": False, "l10": True},
            ]},
            "rocks": {},
        }
        text = _build_section_text(rendered, {"sales": {"rocks": [], "projects": []}},
                                   routing, REGISTRY)
        assert "Demand NRR" in text
        assert "Pipeline Coverage" not in text

    def test_ceiling_blocks_lying_toggle_on_every_surface(self):
        from lib.deck_writer import _filter_visible_rows
        lying = {"metrics": {"founders": [
            {"metric": "Revenue YTD", "slack": True, "deck": True, "doc": True, "l10": True}]},
            "rocks": {}}
        rows = [_row("Revenue YTD", "founders", sensitivity="founders_only")]
        assert _filter_visible_rows(rows, "deck", lying, REGISTRY) == []
        assert _filter_visible_rows(rows, "doc", lying, REGISTRY) == []


class TestDeptLoopConsumesRouting:
    def _run_main(self, routing, registry):
        """Run main() with everything faked; return rendered_per_dept."""
        with patch.object(mku, "load_routing", return_value=routing), \
             patch.object(mku, "_load_registry_for_routing", return_value=registry), \
             patch.object(mku, "get_company_metrics", return_value={}), \
             patch.object(mku, "get_rock_project_progress", return_value={
                 "available": True, "rocks": [], "projects": []}), \
             patch.object(mku, "render_one_row",
                          side_effect=lambda e, d, cm, t: _row(e["key"], d)), \
             patch.object(mku, "run_preflight", return_value=None):
            fake_db = MagicMock()
            ref = fake_db.collection.return_value.document.return_value
            ref.get.return_value.exists = False
            return mku.main(
                skip_deck=True, skip_rocks_deck=True, skip_slack=True,
                include_leadership_doc=False,
                firestore_client=fake_db, input_fn=lambda _: "y",
            )

    def test_membership_and_order_come_from_store(self):
        rendered = self._run_main(ROUTING, REGISTRY)
        assert "sales" in rendered
        names = [r.metric_name for r in rendered["sales"]["scorecard_rows"]]
        assert names == ["Demand NRR", "Pipeline Coverage"]  # store order

    def test_all_dark_dept_is_skipped(self):
        # founders: every surface toggle False + no rocks -> no section at all
        rendered = self._run_main(ROUTING, REGISTRY)
        assert "founders" not in rendered

    def test_routing_unavailable_aborts_before_any_write(self):
        from data.routing_manager import RoutingUnavailableError
        with patch.object(mku, "load_routing",
                          side_effect=RoutingUnavailableError("doc missing")):
            with pytest.raises(RoutingUnavailableError):
                mku.main(skip_deck=True, skip_rocks_deck=True, skip_slack=True,
                         include_leadership_doc=False, input_fn=lambda _: "y")


class TestContractRegistryPath:
    def test_load_registry_honors_kpi_dashboard_repo(self, monkeypatch, tmp_path):
        from lib import metric_contract
        fake_repo = tmp_path / "repo"
        (fake_repo / "dashboard" / "data").mkdir(parents=True)
        (fake_repo / "dashboard" / "data" / "metric_registry.py").write_text(
            "METRIC_REGISTRY = {'Sentinel Metric': {}}\n"
        )
        monkeypatch.setenv("KPI_DASHBOARD_REPO", str(fake_repo))
        metric_contract.clear_registry_cache()
        try:
            registry = metric_contract._load_registry()
            assert "Sentinel Metric" in registry
        finally:
            metric_contract.clear_registry_cache()
