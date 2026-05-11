"""Failure-channel signal for /monday-kpi-update.

Per v3.8 Patch 4 + reference_cron_alerts_channel.md (closes B7 partial-deck silent
failure, B8 missing failure signal, B9 funnel pre-fetch silent failure):
failures alert #kpi-dashboard-notifications (C0AN5N36HDM) with @-mention to
Deuce + Leo.

This deliberately POSTs directly via chat.postMessage rather than reusing the
cron's post_to_slack(), which reads SLACK_CHANNEL from env and would route
failure alerts to the regular pulse channel by mistake.

User IDs are placeholders (U_DEUCE, U_LEO) — resolve via Slack admin lookup
before first production run. Slash command falls back to <!here> if either
env var is missing rather than failing the alert.
"""
import os
import sys
from typing import Optional

SLACK_FAILURE_CHANNEL = "C0AN5N36HDM"  # #kpi-dashboard-notifications
_SLACK_TOKEN_ENV = "SLACK_BOT_TOKEN"
_DEUCE_USER_ID_ENV = "SLACK_USER_ID_DEUCE"
_LEO_USER_ID_ENV = "SLACK_USER_ID_LEO"


def _build_mentions() -> str:
    deuce = os.environ.get(_DEUCE_USER_ID_ENV)
    leo = os.environ.get(_LEO_USER_ID_ENV)
    parts = []
    if deuce:
        parts.append(f"<@{deuce}>")
    if leo:
        parts.append(f"<@{leo}>")
    return " ".join(parts) if parts else "<!here>"


def emit_failure_alert(
    *,
    surface: str,
    detail: str,
    exc: Optional[BaseException] = None,
    dept: Optional[str] = None,
    slide_idx: Optional[int] = None,
) -> None:
    """POST a failure summary to #kpi-dashboard-notifications.

    Never raises — if the alert post itself fails, prints to stderr instead so
    the original failure path can continue (per Patch 4 "do NOT recurse on
    failure here" rule).
    """
    parts = [f"{_build_mentions()} *monday-kpi-update FAILURE*"]
    parts.append(f"• surface: `{surface}`")
    if dept:
        parts.append(f"• dept: `{dept}`")
    if slide_idx is not None:
        parts.append(f"• slide: `{slide_idx}`")
    parts.append(f"• detail: {detail}")
    if exc is not None:
        parts.append(f"• exc: `{type(exc).__name__}: {exc}`")
    text = "\n".join(parts)

    try:
        _post_text_to_failure_channel(text)
    except Exception as e:  # noqa: BLE001 — never recurse on alert failure
        print(f"FAILURE-ALERT itself failed: {e}", file=sys.stderr)
        print(f"Original alert payload:\n{text}", file=sys.stderr)


def _post_text_to_failure_channel(text: str) -> None:
    import httpx  # imported lazily so unit tests can mock it

    token = os.environ.get(_SLACK_TOKEN_ENV)
    if not token:
        raise RuntimeError(f"{_SLACK_TOKEN_ENV} not set; cannot POST failure alert")

    resp = httpx.post(
        "https://slack.com/api/chat.postMessage",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=utf-8",
        },
        json={"channel": SLACK_FAILURE_CHANNEL, "text": text},
        timeout=15.0,
    )
    data = resp.json() if resp.content else {}
    if not data.get("ok"):
        raise RuntimeError(
            f"Slack chat.postMessage error: {data.get('error', 'unknown')} "
            f"(HTTP {resp.status_code})"
        )
