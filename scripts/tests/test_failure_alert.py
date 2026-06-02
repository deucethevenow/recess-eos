"""Contract tests for emit_failure_alert mention behavior.

The @here ping is appropriate for data-write failures (deck/slack/leadership-doc
corruption needs immediate eyes) but noisy for preflight (template/config issues
that just need the owner). _QUIET_SURFACES gates that.
"""
from unittest.mock import patch

import pytest

from lib import failure_alert


@pytest.fixture
def captured_posts(monkeypatch):
    """Replace the Slack POST with a capturing stub so tests assert text only."""
    captured = []

    def fake_post(text):
        captured.append(text)

    monkeypatch.setattr(failure_alert, "_post_text_to_failure_channel", fake_post)
    return captured


def test_emit_failure_alert_uses_at_here_when_no_user_ids_set(
    captured_posts, monkeypatch
):
    """Default behavior: when neither SLACK_USER_ID_DEUCE nor SLACK_USER_ID_LEO
    is set, deck failures fall back to <!here> so someone notices."""
    monkeypatch.delenv("SLACK_USER_ID_DEUCE", raising=False)
    monkeypatch.delenv("SLACK_USER_ID_LEO", raising=False)
    failure_alert.emit_failure_alert(surface="deck", detail="broken")
    assert len(captured_posts) == 1
    assert "<!here>" in captured_posts[0]


def test_emit_failure_alert_skips_at_here_for_preflight_surface(
    captured_posts, monkeypatch
):
    """Preflight failures should NOT page the whole channel — they're config
    issues, not corruption. Without user IDs, the mention is empty (no fallback)."""
    monkeypatch.delenv("SLACK_USER_ID_DEUCE", raising=False)
    monkeypatch.delenv("SLACK_USER_ID_LEO", raising=False)
    failure_alert.emit_failure_alert(surface="preflight", detail="row mismatch")
    assert len(captured_posts) == 1
    assert "<!here>" not in captured_posts[0]
    assert "monday-kpi-update FAILURE" in captured_posts[0]


def test_emit_failure_alert_uses_user_ids_for_preflight_when_set(
    captured_posts, monkeypatch
):
    """If user IDs are set, preflight still pings them — we just skip <!here>."""
    monkeypatch.setenv("SLACK_USER_ID_DEUCE", "U_DEUCE_X")
    monkeypatch.setenv("SLACK_USER_ID_LEO", "U_LEO_X")
    failure_alert.emit_failure_alert(surface="preflight", detail="row mismatch")
    assert len(captured_posts) == 1
    msg = captured_posts[0]
    assert "<@U_DEUCE_X>" in msg
    assert "<@U_LEO_X>" in msg
    assert "<!here>" not in msg


def test_emit_failure_alert_uses_user_ids_for_deck_when_set(
    captured_posts, monkeypatch
):
    """User IDs preferred over <!here> for non-quiet surfaces too."""
    monkeypatch.setenv("SLACK_USER_ID_DEUCE", "U_DEUCE_X")
    monkeypatch.delenv("SLACK_USER_ID_LEO", raising=False)
    failure_alert.emit_failure_alert(surface="deck", detail="write failed")
    msg = captured_posts[0]
    assert "<@U_DEUCE_X>" in msg
    assert "<!here>" not in msg


def test_emit_failure_alert_handles_post_exception_silently(monkeypatch, capsys):
    """If the alert POST itself fails, we print to stderr — never raise."""

    def boom(text):
        raise RuntimeError("slack down")

    monkeypatch.setattr(failure_alert, "_post_text_to_failure_channel", boom)
    # Should NOT raise even though the post fails
    failure_alert.emit_failure_alert(surface="deck", detail="x")
    err = capsys.readouterr().err
    assert "FAILURE-ALERT itself failed" in err
