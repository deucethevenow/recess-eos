"""Patch 4 contract tests — failure-channel signal.

Per Patch 4, failures alert #kpi-dashboard-notifications (C0AN5N36HDM). The
deck per-slide writer (out of scope for Session 2) consumes the same
emit_failure_alert API; this test file covers the wrapper's contract surface.
"""
from lib import failure_alert
from lib.failure_alert import SLACK_FAILURE_CHANNEL, emit_failure_alert


def test_failure_channel_is_kpi_dashboard_notifications():
    """The channel ID is hard-locked to #kpi-dashboard-notifications per
    reference_cron_alerts_channel.md. A regression that routes alerts to a
    different channel would silently break the on-call signal."""
    assert SLACK_FAILURE_CHANNEL == "C0AN5N36HDM"


def test_emit_failure_alert_posts_to_failure_channel(monkeypatch):
    captured = {}

    def fake_post(text):
        captured["text"] = text

    monkeypatch.setattr(failure_alert, "_post_text_to_failure_channel", fake_post)
    emit_failure_alert(surface="deck", detail="boom", dept="sales", slide_idx=33)
    assert "monday-kpi-update FAILURE" in captured["text"]
    assert "surface: `deck`" in captured["text"]
    assert "dept: `sales`" in captured["text"]
    assert "slide: `33`" in captured["text"]
    assert "boom" in captured["text"]


def test_emit_failure_alert_includes_exception_type_and_message(monkeypatch):
    captured = {}
    monkeypatch.setattr(
        failure_alert, "_post_text_to_failure_channel", lambda text: captured.setdefault("text", text)
    )
    try:
        raise ValueError("BQ timeout")
    except ValueError as e:
        emit_failure_alert(surface="bq", detail="query failed", exc=e)
    assert "ValueError: BQ timeout" in captured["text"]


def test_emit_failure_alert_does_not_raise_when_post_fails(monkeypatch):
    """If the alert POST itself fails, the original failure path must not be
    further blocked. Per Patch 4: 'do NOT recurse on failure here — print to
    stderr if THIS post fails.'"""
    def boom(text):
        raise RuntimeError("Slack down")

    monkeypatch.setattr(failure_alert, "_post_text_to_failure_channel", boom)
    # Must not raise.
    emit_failure_alert(surface="anything", detail="ok")


def test_emit_failure_alert_falls_back_to_here_when_user_ids_unset(monkeypatch):
    captured = {}
    monkeypatch.delenv("SLACK_USER_ID_DEUCE", raising=False)
    monkeypatch.delenv("SLACK_USER_ID_LEO", raising=False)
    monkeypatch.setattr(failure_alert, "_post_text_to_failure_channel", lambda text: captured.setdefault("text", text))
    emit_failure_alert(surface="x", detail="y")
    assert "<!here>" in captured["text"]


def test_emit_failure_alert_uses_user_mentions_when_env_set(monkeypatch):
    captured = {}
    monkeypatch.setenv("SLACK_USER_ID_DEUCE", "U123DEUCE")
    monkeypatch.setenv("SLACK_USER_ID_LEO", "U456LEO")
    monkeypatch.setattr(failure_alert, "_post_text_to_failure_channel", lambda text: captured.setdefault("text", text))
    emit_failure_alert(surface="x", detail="y")
    assert "<@U123DEUCE>" in captured["text"]
    assert "<@U456LEO>" in captured["text"]


