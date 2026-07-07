"""P3.1 — sync fallback-stamps quarter + project_type when Asana fields are empty.

Plan: kpi-dashboard context/plans/2026-07-06-metric-routing.md Phase 3.
Root cause being fixed: the July 6 NULLs exist because the Q3 portfolio's
"Project Type"/"Quarter" custom fields are EMPTY, and the dashboard's legacy
name-sniff expects the Q2 "Rock N:" prefix — "Q3 Rock: ..." names classify as
projects (the 0-rocks bug). Regression fixture = the REAL 17 Q3 names.
"""
import re

from lib.sync_projects import (
    asana_project_to_bq_row,
    derive_quarter_from_portfolio_name,
    derive_project_type_from_name,
    normalize_quarter_value,
)


# The REAL Q3 2026 portfolio as of 2026-07-06 (17 projects; 9 are rocks).
REAL_Q3_NAMES = [
    "Achieve Q3 Key Supply Target Moment Goals",
    "Q3 Rock: Lindy Workflows — Reduce Manual Emails 40%",
    "Q3 Rock: Enterprise Organizer Reports — Partner-Facing Execution Hubs Live",
    "Q3 Rock: AM Ops Automation - Shipping Sheet, Master Advance, Vendor Reminders",
    "Customer Advisory Board (Marketing Rock — Q3 2026)",
    "Standardize Brand Onboarding & Activation Process + Template Library",
    "Q3 Rock: Test Influencer Content Capture at 10 Events — Build the Playbook",
    "Set Up API Hosting Service — Off Heroku (Engineering 2026-Q3)",
    "Fast-Track Harness : Asana Task —> Preview (Engineering 2026-Q3)",
    "Feature-Branch Previews — QA & UAT (Engineering 2026-Q3)",
    "Preview Deploys on New Cloud Provider (Engineering 2026-Q3)",
    "Migrate Vue to Vite 8 + CI Testing (Engineering 2026-Q3)",
    "Code Quality Checks on Pull Requests (Engineering 2026-Q3)",
    "DataDog Dashboards, Alerts + Noise Cleanup (Engineering 2026-Q3)",
    "Q3 Rock: 12 2027 Planning Meetings — Andy",
    "Q3 Rock: 12 2027 Planning Meetings — Danny",
    "Q3 Rock: 12 2027 Planning Meetings — Katie",
]


class TestQuarterFromPortfolioName:
    def test_q3_2026_portfolio_parses(self):
        assert derive_quarter_from_portfolio_name("Q3 2026 Rocks + Projects") == "2026-Q3"

    def test_other_quarters_parse(self):
        assert derive_quarter_from_portfolio_name("Q1 2027 Rocks + Projects") == "2027-Q1"
        assert derive_quarter_from_portfolio_name("Q4 2026 Rocks + Projects") == "2026-Q4"

    def test_non_matching_name_returns_none(self):
        assert derive_quarter_from_portfolio_name("Recess OS Projects") is None
        assert derive_quarter_from_portfolio_name("") is None
        assert derive_quarter_from_portfolio_name(None) is None


class TestProjectTypeFromName:
    def test_at_least_8_of_the_real_q3_names_classify_rock(self):
        # Regression pin for the name-prefix bug: Q2 used "Rock N:" prefixes,
        # Q3 uses "Q3 Rock:" / "(Marketing Rock — Q3 2026)" mid-name forms.
        rocks = [n for n in REAL_Q3_NAMES if derive_project_type_from_name(n) == "rock"]
        assert len(rocks) >= 8, f"only {len(rocks)} classified rock: {rocks}"

    def test_supply_rock_is_the_known_name_unclassifiable_one(self):
        # "Achieve Q3 Key Supply Target Moment Goals" is a rock by INTENT but
        # carries no word "rock" — name derivation classifies it "project"
        # until its Asana "Project Type" field is set (fields always win).
        # This pins the plan's deliberate ">=8" gate (8 name-classifiable of
        # the 9 actual rocks) and documents the one-field manual fix.
        rocks = [n for n in REAL_Q3_NAMES if derive_project_type_from_name(n) == "rock"]
        assert len(rocks) == 8
        assert "Achieve Q3 Key Supply Target Moment Goals" not in rocks

    def test_engineering_projects_stay_projects(self):
        for name in REAL_Q3_NAMES:
            if "(Engineering 2026-Q3)" in name:
                assert derive_project_type_from_name(name) == "project", name

    def test_q2_style_prefix_still_rock(self):
        assert derive_project_type_from_name("Rock 003: Close the Books Faster") == "rock"

    def test_whole_word_only_no_rockstar_matches(self):
        assert derive_project_type_from_name("RockStar Hiring Sprint") == "project"
        assert derive_project_type_from_name("Rockets & Rollouts") == "project"


class TestQuarterValueNormalization:
    """kpi-critic 2026-07-07: a human-entered 'Q3 2026' in the Asana Quarter
    field must normalize to the canonical 'YYYY-Qn' the dashboard filter
    compares against — otherwise the rock is silently dropped (the exact
    0-rocks failure class this phase exists to kill)."""

    def test_canonical_passes_through(self):
        assert normalize_quarter_value("2026-Q3") == "2026-Q3"

    def test_human_orderings_normalize(self):
        assert normalize_quarter_value("Q3 2026") == "2026-Q3"
        assert normalize_quarter_value("q3-2026") == "2026-Q3"
        assert normalize_quarter_value("2026 Q3") == "2026-Q3"
        assert normalize_quarter_value(" Q4 2027 ") == "2027-Q4"

    def test_garbage_returns_none_so_fallback_applies(self):
        assert normalize_quarter_value("next quarter") is None
        assert normalize_quarter_value("Q5 2026") is None
        assert normalize_quarter_value("") is None
        assert normalize_quarter_value(None) is None

    def test_row_stamping_normalizes_field_and_falls_back_on_garbage(self):
        proj = {"gid": "g", "name": "Some Project", "owner": None,
                "custom_fields": [{"name": "Quarter", "gid": "cf", "text_value": "Q3 2026"}],
                "_task_count": 0, "_completion_percent": 0.0,
                "modified_at": "2026-07-07T00:00:00Z"}
        row = asana_project_to_bq_row(proj, quarter_fallback="2026-Q1")
        assert row["quarter"] == "2026-Q3"  # normalized field wins
        proj["custom_fields"][0]["text_value"] = "sometime soon"
        row = asana_project_to_bq_row(proj, quarter_fallback="2026-Q1")
        assert row["quarter"] == "2026-Q1"  # garbage -> fallback, never verbatim


class TestRowFallbackStamping:
    def _project(self, name, custom_fields=None):
        return {"gid": "g1", "name": name, "owner": {"email": "x@recess.is", "name": "X"},
                "custom_fields": custom_fields or [], "_task_count": 3,
                "_completion_percent": 10.0, "modified_at": "2026-07-06T00:00:00Z"}

    def test_empty_fields_get_fallback_stamps(self):
        row = asana_project_to_bq_row(
            self._project("Q3 Rock: Lindy Workflows — Reduce Manual Emails 40%"),
            quarter_fallback="2026-Q3",
        )
        assert row["quarter"] == "2026-Q3"
        assert row["project_type"] == "rock"

    def test_engineering_project_stamps_project(self):
        row = asana_project_to_bq_row(
            self._project("Migrate Vue to Vite 8 + CI Testing (Engineering 2026-Q3)"),
            quarter_fallback="2026-Q3",
        )
        assert row["project_type"] == "project"

    def test_populated_asana_fields_win_over_fallbacks(self):
        cf = [
            {"name": "Project Type", "gid": "cf1", "enum_value": {"name": "Rock"}},
            {"name": "Quarter", "gid": "cf2", "text_value": "2026-Q4"},
        ]
        row = asana_project_to_bq_row(
            self._project("Some Ordinary Project Name", custom_fields=cf),
            quarter_fallback="2026-Q3",
        )
        assert row["project_type"] == "Rock"     # field value passes through untouched
        assert row["quarter"] == "2026-Q4"       # field wins over portfolio fallback

    def test_no_fallback_available_stamps_project_and_keeps_quarter_null(self):
        row = asana_project_to_bq_row(self._project("Mystery Item"), quarter_fallback=None)
        assert row["project_type"] == "project"  # type ALWAYS stamped (never NULL again)
        assert row["quarter"] is None            # quarter honest-NULL when unparseable
