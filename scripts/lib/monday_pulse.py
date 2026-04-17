"""Monday Pulse — Slack consumer for weekly KPI metrics.

Renders a single Slack message with per-department metric sections.
Consumes MetricPayload objects built by the orchestrator — no BQ access,
no transforms, no formatting logic. Pure consumer.

Architecture:
    render_monday_pulse()  →  pure render (Slack Block Kit JSON)
    post_monday_pulse()    →  thin Slack I/O wrapper
"""

from datetime import datetime
from typing import Optional

from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

from lib.metric_payloads import MetricPayload, SENSITIVITY_LEVELS
from lib.orchestrator import ConsumerResult


class SlackPostError(Exception):
    """Raised when Slack API rejects the message."""


def extract_metric_display_value(payload: MetricPayload) -> str:
    """Extract display value for Slack rendering.

    Returns payload.display_value with a [stale] badge appended
    if availability_state == "stale". Other states (needs_build, null)
    pass through their display_value unchanged.

    Exists as a standalone function for cross-output consistency test import.
    """
    value = payload.display_value
    if payload.availability_state == "stale":
        value = value + " [stale]"
    return value


def render_monday_pulse(
    all_payloads: dict[str, list[MetricPayload]],
    snapshot_timestamp: str,
    meeting_configs: list[dict],
    project_data: list[dict] = None,
) -> tuple[list[dict], list[ConsumerResult]]:
    """Render Monday Pulse as Slack Block Kit blocks.

    - Filters to public sensitivity (founders_only and leadership excluded)
    - Renders needs_build with badge, stale with [stale] suffix, null as dash
    - Single message with sections per department
    - Returns (blocks, list[ConsumerResult]) — one result per metric processed
    """
    blocks: list[dict] = []
    results: list[ConsumerResult] = []

    if not all_payloads or not meeting_configs:
        return blocks, results

    # Parse timestamp for header
    try:
        ts_dt = datetime.fromisoformat(snapshot_timestamp.replace("Z", "+00:00"))
        date_str = ts_dt.strftime("%b %-d, %Y")
    except (ValueError, TypeError):
        date_str = snapshot_timestamp

    # Header block
    blocks.append({
        "type": "section",
        "text": {
            "type": "mrkdwn",
            "text": ":chart_with_upwards_trend: *Monday Pulse* \u2014 " + date_str,
        },
    })

    # Build a meeting_id → config lookup for ordering
    meeting_map = {m["id"]: m for m in meeting_configs}

    # Iterate meetings in config order (not dict order)
    for meeting_cfg in meeting_configs:
        dept_id = meeting_cfg["id"]
        dept_payloads = all_payloads.get(dept_id, [])
        if not dept_payloads:
            continue

        dept_name = meeting_cfg.get("name", dept_id)

        # Separate public vs filtered metrics
        metric_lines = []
        for p in dept_payloads:
            sensitivity_level = SENSITIVITY_LEVELS.get(p.sensitivity, 0)
            # Monday Pulse = public channel. Only include public metrics.
            if sensitivity_level > SENSITIVITY_LEVELS["public"]:
                results.append(ConsumerResult(
                    registry_key=p.registry_key,
                    dept_id=dept_id,
                    consumer="slack_pulse",
                    action="skipped",
                    error_message="sensitivity filtered (not public)",
                ))
                continue

            display = extract_metric_display_value(p)

            # Format: "Metric Name: *value* (target: X)" or just "Metric Name: *value*"
            line = p.metric_name + ": *" + display + "*"
            if p.target is not None and p.availability_state not in ("needs_build", "null"):
                target_display = _format_target(p.target, p.format_spec)
                line = line + " (target: " + target_display + ")"

            metric_lines.append(line)
            results.append(ConsumerResult(
                registry_key=p.registry_key,
                dept_id=dept_id,
                consumer="slack_pulse",
                action="delivered",
            ))

        if metric_lines:
            section_text = "*" + dept_name + "*\n" + "\n".join(metric_lines)
            blocks.append({
                "type": "section",
                "text": {"type": "mrkdwn", "text": section_text},
            })

    # Rock / Project progress section (from eos_projects via sync-to-bq)
    if project_data:
        rocks = [p for p in project_data if "Rock" in (p.get("name") or "")]
        projects = [p for p in project_data if p not in rocks]

        if rocks:
            rock_lines = []
            for r in sorted(rocks, key=lambda x: x.get("name", "")):
                pct = r.get("completion_percent", 0) or 0
                owner = (r.get("owner_name") or "").split()[0]  # first name only
                name = r.get("name", "?")
                rock_lines.append(f"{name}: *{pct:.0f}%* ({owner})")
            blocks.append({
                "type": "section",
                "text": {"type": "mrkdwn", "text": "*Q2 Rocks*\n" + "\n".join(rock_lines)},
            })

        if projects:
            proj_lines = []
            for p in sorted(projects, key=lambda x: x.get("name", "")):
                pct = p.get("completion_percent", 0) or 0
                owner = (p.get("owner_name") or "").split()[0]
                name = p.get("name", "?")
                proj_lines.append(f"{name}: *{pct:.0f}%* ({owner})")
            blocks.append({
                "type": "section",
                "text": {"type": "mrkdwn", "text": "*Projects*\n" + "\n".join(proj_lines)},
            })

    # If no metric sections were added (all filtered), return empty blocks
    # to avoid posting a header + footer with no content
    if len(blocks) <= 1:  # only header, no dept sections
        return [], results

    # Footer with data timestamp
    blocks.append({
        "type": "section",
        "text": {
            "type": "mrkdwn",
            "text": "_Data as of " + snapshot_timestamp + "_",
        },
    })

    return blocks, results


def post_monday_pulse(
    blocks: list[dict],
    channel_id: str,
    slack_token: str,
    dry_run: bool = False,
) -> str:
    """Post Block Kit blocks to Slack.

    Returns message_ts on success, or "dry_run" if dry_run=True.
    Raises SlackPostError on API failure.
    """
    if dry_run:
        return "dry_run"

    client = WebClient(token=slack_token)
    try:
        response = client.chat_postMessage(
            channel=channel_id,
            blocks=blocks,
            text="Monday Pulse",  # fallback for notifications
        )
        return response.data.get("ts", "")
    except SlackApiError as e:
        raise SlackPostError(
            "Slack API error posting Monday Pulse: " + str(e)
        ) from e


def _format_target(target: float, format_spec: str) -> str:
    """Format a target value for inline display in Slack."""
    if format_spec == "percent":
        if abs(target) <= 1:
            return str(round(target * 100, 1)) + "%"
        return str(round(target, 1)) + "%"
    elif format_spec in ("multiplier", "pipeline_gap"):
        return str(round(target, 1)) + "x"
    elif format_spec == "currency":
        if abs(target) >= 1_000_000:
            return "$" + str(round(target / 1_000_000, 1)) + "M"
        elif abs(target) >= 1_000:
            return "$" + str(round(target / 1_000)) + "K"
        return "$" + str(round(target))
    elif format_spec == "days":
        return str(round(target)) + " days"
    elif format_spec in ("count", "number"):
        return "{:,.0f}".format(target)
    elif format_spec == "number_millions":
        return str(round(target / 1_000_000, 1)) + "M"
    return str(target)
