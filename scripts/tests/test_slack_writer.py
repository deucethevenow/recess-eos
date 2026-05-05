"""Session 3 contract tests — slack_writer.

Asserts the contract surface of post_pulse:
  1. Skips and returns None when Firestore marker is set.
  2. Posts via injected post_fn with explicit channel (no env-var routing).
  3. Marks Firestore ONLY on successful post.
  4. founders_only rows are filtered before composing blocks.
  5. Phase 11: VERIFY_SLACK_CHANNEL is C0AN5N36HDM (kpi-dashboard-notifications).
"""
from datetime import date
from unittest.mock import MagicMock

import pytest

from lib.rendered_row import RenderedRow
from lib.slack_writer import post_pulse


def _row(name, sensitivity="public", display="$1"):
    return RenderedRow(
        metric_name=name,
        display_label=name,
        dept_id="leadership",
        sensitivity=sensitivity,
        actual_raw=None,
        target_raw=None,
        status_icon="⚪",
        display=display,
        actual_display=display,
        target_display=None,
        trend_display=None,
        is_phase2_placeholder=False,
        is_special_override=False,
    )


def _make_firestore_with_marker(marker_present):
    fake_db = MagicMock()
    doc = MagicMock()
    doc.exists = bool(marker_present)
    doc.to_dict.return_value = {"slack_posted": True} if marker_present else {}
    fake_db.collection.return_value.document.return_value.get.return_value = doc
    return fake_db


# ----- Idempotency: skip when marker present ------------------------------- #


def test_post_pulse_skips_when_marker_already_set(capsys):
    rendered = {"leadership": {"scorecard_rows": [_row("X")]}}
    rocks = {"leadership": {"rocks": [], "projects": []}}

    post_calls = []

    def fake_post(*, channel_id, blocks):
        post_calls.append((channel_id, blocks))
        return "TS_NEW"

    fake_db = _make_firestore_with_marker(marker_present=True)

    result = post_pulse(
        rendered_per_dept=rendered,
        rocks_by_dept=rocks,
        channel_id="C_TEST",
        run_date=date(2026, 5, 5),
        post_fn=fake_post,
        firestore_client=fake_db,
    )

    assert result is None
    assert post_calls == []
    out = capsys.readouterr().out
    assert "already posted" in out.lower()


def test_post_pulse_posts_and_marks_when_no_marker(monkeypatch):
    rendered = {"leadership": {"scorecard_rows": [_row("X")]}}
    rocks = {"leadership": {"rocks": [], "projects": []}}

    post_calls = []

    def fake_post(*, channel_id, blocks):
        post_calls.append((channel_id, blocks))
        return "TS_OK"

    fake_db = _make_firestore_with_marker(marker_present=False)
    fake_doc_ref = fake_db.collection.return_value.document.return_value

    # Force monday_kpi_update + post_monday_pulse to import BEFORE we mock
    # google.cloud — post_monday_pulse depends on real google.cloud.exceptions
    # at module load. Once cached in sys.modules, the mock is harmless.
    import monday_kpi_update  # noqa: F401

    # Prevent google.cloud.firestore real import inside mark_slack_posted.
    fake_firestore = MagicMock()
    fake_firestore.SERVER_TIMESTAMP = "SENTINEL"
    monkeypatch.setitem(
        __import__("sys").modules,
        "google.cloud",
        MagicMock(firestore=fake_firestore),
    )
    monkeypatch.setitem(
        __import__("sys").modules, "google.cloud.firestore", fake_firestore
    )

    result = post_pulse(
        rendered_per_dept=rendered,
        rocks_by_dept=rocks,
        channel_id="C_TEST",
        run_date=date(2026, 5, 5),
        post_fn=fake_post,
        firestore_client=fake_db,
    )

    assert result == "TS_OK"
    assert len(post_calls) == 1
    assert post_calls[0][0] == "C_TEST"
    # Marker write happened with merge=True
    args, kwargs = fake_doc_ref.set.call_args
    assert kwargs == {"merge": True}
    payload = args[0]
    assert payload["slack_posted"] is True
    assert payload["ts"] == "TS_OK"
    assert payload["channel"] == "C_TEST"


def test_post_pulse_does_not_mark_on_post_failure(monkeypatch):
    """Failed Slack post leaves the marker absent so a retry can post."""
    rendered = {"leadership": {"scorecard_rows": [_row("X")]}}
    rocks = {"leadership": {"rocks": [], "projects": []}}

    def boom(*, channel_id, blocks):
        raise RuntimeError("Slack down")

    fake_db = _make_firestore_with_marker(marker_present=False)
    fake_doc_ref = fake_db.collection.return_value.document.return_value

    with pytest.raises(RuntimeError, match="Slack down"):
        post_pulse(
            rendered_per_dept=rendered,
            rocks_by_dept=rocks,
            channel_id="C_TEST",
            run_date=date(2026, 5, 5),
            post_fn=boom,
            firestore_client=fake_db,
        )

    # Firestore .set was NOT called — marker absent.
    fake_doc_ref.set.assert_not_called()


# ----- founders_only filter ----------------------------------------------- #


def test_post_pulse_filters_founders_only_from_blocks(monkeypatch):
    rendered = {
        "leadership": {
            "scorecard_rows": [
                _row("Public", "public", display="$100"),
                _row("Sensitive", "founders_only", display="$200"),
            ]
        }
    }
    rocks = {"leadership": {"rocks": [], "projects": []}}

    captured_blocks = []

    def fake_post(*, channel_id, blocks):
        captured_blocks.extend(blocks)
        return "TS_OK"

    fake_db = _make_firestore_with_marker(marker_present=False)
    fake_firestore = MagicMock()
    fake_firestore.SERVER_TIMESTAMP = "SENTINEL"
    monkeypatch.setitem(
        __import__("sys").modules,
        "google.cloud",
        MagicMock(firestore=fake_firestore),
    )
    monkeypatch.setitem(
        __import__("sys").modules, "google.cloud.firestore", fake_firestore
    )

    post_pulse(
        rendered_per_dept=rendered,
        rocks_by_dept=rocks,
        channel_id="C_TEST",
        run_date=date(2026, 5, 5),
        post_fn=fake_post,
        firestore_client=fake_db,
    )

    full_text = "\n".join(
        b.get("text", {}).get("text", "")
        for b in captured_blocks
        if b.get("type") == "section"
    )
    assert "Public" in full_text
    assert "Sensitive" not in full_text
    assert "$200" not in full_text


# ----- Phase 11 channel routing ------------------------------------------- #


def test_post_pulse_uses_explicit_channel_not_env(monkeypatch):
    """Patch 11: The slash command must target a test channel during Week 1
    verify regardless of the SLACK_CHANNEL env var (which routes the cron)."""
    rendered = {"leadership": {"scorecard_rows": [_row("X")]}}
    rocks = {"leadership": {"rocks": [], "projects": []}}

    monkeypatch.setenv("SLACK_CHANNEL", "C_FROM_ENV_DO_NOT_USE")

    captured = {}

    def fake_post(*, channel_id, blocks):
        captured["channel"] = channel_id
        return "TS"

    fake_db = _make_firestore_with_marker(marker_present=False)
    fake_firestore = MagicMock()
    fake_firestore.SERVER_TIMESTAMP = "SENTINEL"
    monkeypatch.setitem(
        __import__("sys").modules,
        "google.cloud",
        MagicMock(firestore=fake_firestore),
    )
    monkeypatch.setitem(
        __import__("sys").modules, "google.cloud.firestore", fake_firestore
    )

    post_pulse(
        rendered_per_dept=rendered,
        rocks_by_dept=rocks,
        channel_id="C_VERIFY",
        run_date=date(2026, 5, 5),
        post_fn=fake_post,
        firestore_client=fake_db,
    )

    assert captured["channel"] == "C_VERIFY"


def test_default_slack_channel_is_verify_during_phase_11():
    """Patch 11 cut-over criterion: DEFAULT_SLACK_CHANNEL must be the VERIFY
    channel during Week 1+. Cut-over is a one-line change to PROD_SLACK_CHANNEL."""
    import monday_kpi_update

    assert monday_kpi_update.DEFAULT_SLACK_CHANNEL == "C0AN5N36HDM"  # #kpi-dashboard-notifications
    assert monday_kpi_update.VERIFY_SLACK_CHANNEL == "C0AN5N36HDM"
    assert monday_kpi_update.PROD_SLACK_CHANNEL == "C0AQP3WH7AB"
