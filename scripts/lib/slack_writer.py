"""Slack writer for /monday-kpi-update.

Per v3.8 Patch 3 (Slack idempotency via Firestore marker) + Patch 11 (cron
transition during which the slash command runs alongside the existing cron):

Surface contract:
  - Consults `idempotency.slack_already_posted_today(run_date)` BEFORE posting.
    Returns None if already posted (no error — the marker is the persistent
    record; a stdout notice goes to the operator running the slash command).
  - Posts via `chat.postMessage` with EXPLICIT channel override. Deliberately
    does NOT reuse `post_monday_pulse.post_to_slack` because that function
    reads `SLACK_CHANNEL` from the environment — during Phase 11 parallel
    verify, the slash command must be able to target a test channel
    independently of whatever the env says.
  - Marks the Firestore doc on success only — a failed post leaves the
    marker absent so a retry can post.

Phase 11 channel routing (Patch 11):
  Week 1+ verify: post to `#kpi-dashboard-notifications` (C0AN5N36HDM) or
  `#kpi-test`. Cut-over after 2 clean Mondays: change the slash command's
  default to `#recess-goals-kpis` (C0AQP3WH7AB).
"""
import os
from datetime import date as _date
from typing import Any, Callable, Dict, List, Optional

from .idempotency import mark_slack_posted, slack_already_posted_today

_SLACK_TOKEN_ENV = "SLACK_BOT_TOKEN"


def _build_slack_blocks(
    rendered_per_dept: Dict[str, Dict[str, Any]],
    rocks_by_dept: Dict[str, Dict[str, list]],
    max_sensitivity: str,
) -> List[Dict[str, Any]]:
    """Compose Block Kit blocks from rendered rows + per-dept rocks/projects.

    Local import of `build_dept_section_for_slack` avoids a circular import
    at module-load (monday_kpi_update imports slack_writer; slack_writer
    needs the helper from monday_kpi_update).
    """
    from monday_kpi_update import build_dept_section_for_slack  # type: ignore

    blocks: List[Dict[str, Any]] = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": "Monday KPI update"},
        }
    ]
    for dept_id, payload in rendered_per_dept.items():
        rocks_section = rocks_by_dept.get(dept_id, {})
        blocks.extend(
            build_dept_section_for_slack(
                dept_id,
                payload.get("scorecard_rows", []),
                rocks_section,
                max_sensitivity,
            )
        )
        blocks.append({"type": "divider"})
    if blocks and blocks[-1].get("type") == "divider":
        blocks.pop()
    return blocks


def _post_chat_post_message(
    channel_id: str,
    blocks: List[Dict[str, Any]],
    post_fn: Optional[Callable] = None,
) -> str:
    """POST blocks to chat.postMessage with explicit channel.

    `post_fn(channel_id, blocks)` injection lets tests skip the httpx
    network call without monkeypatching httpx itself.
    """
    if post_fn is not None:
        return post_fn(channel_id=channel_id, blocks=blocks)

    import httpx  # imported lazily so unit tests can avoid the dependency

    token = os.environ.get(_SLACK_TOKEN_ENV)
    if not token:
        raise RuntimeError(
            f"{_SLACK_TOKEN_ENV} not set; cannot POST pulse to Slack."
        )
    resp = httpx.post(
        "https://slack.com/api/chat.postMessage",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=utf-8",
        },
        json={"channel": channel_id, "blocks": blocks},
        timeout=15.0,
    )
    data = resp.json() if resp.content else {}
    if not data.get("ok"):
        raise RuntimeError(
            f"Slack chat.postMessage error: {data.get('error', 'unknown')} "
            f"(HTTP {resp.status_code})"
        )
    return data.get("ts", "")


def post_pulse(
    *,
    rendered_per_dept: Dict[str, Dict[str, Any]],
    rocks_by_dept: Dict[str, Dict[str, list]],
    channel_id: str,
    run_date: _date,
    max_sensitivity: str = "public",
    post_fn: Optional[Callable] = None,
    firestore_client: Any = None,
) -> Optional[str]:
    """Post the pulse Block Kit to `channel_id`, idempotent on `run_date`.

    Returns:
      - the Slack ts string on first successful post
      - None if `slack_already_posted_today(run_date)` is True (no-op)

    Failures (network, Slack API error, Firestore error) propagate as
    exceptions — the caller in `monday_kpi_update.main()` wraps them with
    `emit_failure_alert(surface="slack", ...)`.
    """
    if slack_already_posted_today(run_date, client=firestore_client):
        print(
            f"[slack] Skipping post — Firestore marker shows pulse already "
            f"posted on {run_date.isoformat()}."
        )
        return None

    blocks = _build_slack_blocks(rendered_per_dept, rocks_by_dept, max_sensitivity)
    ts = _post_chat_post_message(channel_id, blocks, post_fn=post_fn)
    mark_slack_posted(run_date, ts=ts, channel=channel_id, client=firestore_client)
    return ts
