"""Cron Dispatch — week-parity routing for bi-weekly consumer schedules.

Determines whether the current week is a "goals" week (push KPI goals to Asana)
or a "projects" week (push project status). Uses ISO week numbers and a
configurable reference week for parity calculation.

Config (in recess_os.yml):
    cron:
      reference_week: 14        # ISO week 14 is first goals week
      goals_weeks: "even"       # even-offset weeks are goals weeks
"""

from datetime import date


class CronConfigError(Exception):
    """Raised when cron config is missing or incomplete."""


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
    goals_weeks = cron_config["goals_weeks"]

    current_week = today.isocalendar()[1]
    offset = current_week - reference_week
    is_even_offset = (offset % 2) == 0

    if goals_weeks == "even":
        return "goals" if is_even_offset else "projects"
    elif goals_weeks == "odd":
        return "goals" if not is_even_offset else "projects"
    else:
        raise CronConfigError(
            "cron.goals_weeks must be 'even' or 'odd', got: " + str(goals_weeks)
        )
