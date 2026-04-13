"""Tests for the cron dispatch module — week-parity routing."""

import sys
import os
from datetime import date

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from lib.cron_dispatch import CronConfigError, get_cron_mode


# ── Known weeks ──────────────────────────────────────────────────��────


def _config(reference_week=14, reference_year=2026, goals_weeks="even"):
    return {
        "cron": {
            "reference_week": reference_week,
            "reference_year": reference_year,
            "goals_weeks": goals_weeks,
        }
    }


class TestGetCronMode:

    def test_known_goals_week(self):
        """ISO week 14 (reference week, even offset 0) → goals."""
        # 2026-03-30 is in ISO week 14
        d = date(2026, 3, 30)
        assert d.isocalendar()[1] == 14
        assert get_cron_mode(d, _config()) == "goals"

    def test_known_projects_week(self):
        """ISO week 15 (odd offset 1) → projects."""
        # 2026-04-07 is in ISO week 15
        d = date(2026, 4, 7)
        assert d.isocalendar()[1] == 15
        assert get_cron_mode(d, _config()) == "projects"

    def test_week_16_back_to_goals(self):
        """ISO week 16 (even offset 2) → goals."""
        # 2026-04-14 is in ISO week 16
        d = date(2026, 4, 14)
        assert d.isocalendar()[1] == 16
        assert get_cron_mode(d, _config()) == "goals"

    def test_missing_cron_section_raises(self):
        with pytest.raises(CronConfigError, match="missing 'cron' section"):
            get_cron_mode(date(2026, 4, 14), {})

    def test_missing_reference_week_raises(self):
        config = {"cron": {"goals_weeks": "even"}}
        with pytest.raises(CronConfigError, match="reference_week"):
            get_cron_mode(date(2026, 4, 14), config)

    def test_missing_goals_weeks_raises(self):
        config = {"cron": {"reference_week": 14}}
        with pytest.raises(CronConfigError, match="goals_weeks"):
            get_cron_mode(date(2026, 4, 14), config)

    def test_odd_parity_inverts_result(self):
        """goals_weeks='odd' flips: week 14 (offset 0, even) → projects."""
        d = date(2026, 3, 30)  # ISO week 14
        assert get_cron_mode(d, _config(goals_weeks="odd")) == "projects"
        # And week 15 (offset 1, odd) → goals
        d2 = date(2026, 4, 7)  # ISO week 15
        assert get_cron_mode(d2, _config(goals_weeks="odd")) == "goals"

    def test_year_boundary_preserves_parity(self):
        """Parity must be continuous across year boundaries (including 53-week years).

        2026 is a 53-week ISO year. Week 52 of 2026 and week 1 of 2027 are
        consecutive, so their parity must differ by exactly 1.
        """
        # Week 52 of 2026: offset from week 14 = 38 (even) → goals
        d_w52 = date.fromisocalendar(2026, 52, 1)
        assert get_cron_mode(d_w52, _config()) == "goals"

        # Week 53 of 2026: offset = 39 (odd) → projects
        d_w53 = date.fromisocalendar(2026, 53, 1)
        assert get_cron_mode(d_w53, _config()) == "projects"

        # Week 1 of 2027: offset = 40 (even) → goals
        d_w1_2027 = date.fromisocalendar(2027, 1, 1)
        assert get_cron_mode(d_w1_2027, _config()) == "goals"
