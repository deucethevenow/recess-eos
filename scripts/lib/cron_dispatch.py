"""Cron Dispatch — week-parity routing for bi-weekly consumer schedules.

Determines whether the current week is a "goals" week (push KPI goals to Asana)
or a "projects" week (push project status). Uses ISO week numbers and a
configurable reference week for parity calculation.

Config (in recess_os.yml):
    cron:
      reference_week: 14        # ISO week 14 is first goals week
      reference_year: 2026      # year of the reference week
      goals_weeks: "even"       # even-offset weeks are goals weeks
"""

from datetime import date


class CronConfigError(Exception):
    """Raised when cron config is missing or incomplete."""


def _iso_week_count(d: date) -> int:
    """Return a monotonically increasing week counter from ISO year/week.

    Uses ISO year * 53 + ISO week as a stable ordinal.
    This ensures parity is preserved across year boundaries,
    including 53-week (long) ISO years.
    """
    iso_year, iso_week, _ = d.isocalendar()
    return iso_year * 53 + iso_week


def get_cron_mode(today: date, config: dict) -> str:
    """Returns 'goals' or 'projects' based on ISO week parity.

    Raises CronConfigError if config["cron"] is missing or incomplete.
    NO silent defaults for reference_week or goals_weeks.
    """
    cron_config = config.get("cron")
    if cron_config is None:
        raise CronConfigError("recess_os.yml missing 'cron' section.")
    if "reference_week" not in cron_config:
        raise CronConfigError("cron config missing 'reference_week'.")
    if "goals_weeks" not in cron_config:
        raise CronConfigError("cron config missing 'goals_weeks'.")

    reference_week = cron_config["reference_week"]
    reference_year = cron_config.get("reference_year", 2026)
    goals_weeks = cron_config["goals_weeks"]

    # Build a reference date from ISO year/week (Monday of that week)
    ref_date = date.fromisocalendar(reference_year, reference_week, 1)

    # Compute offset using stable week counter (handles year boundaries)
    offset = _iso_week_count(today) - _iso_week_count(ref_date)
    is_even_offset = (offset % 2) == 0

    if goals_weeks == "even":
        return "goals" if is_even_offset else "projects"
    elif goals_weeks == "odd":
        return "goals" if not is_even_offset else "projects"
    else:
        raise CronConfigError(
            "cron.goals_weeks must be 'even' or 'odd', got: " + str(goals_weeks)
        )
