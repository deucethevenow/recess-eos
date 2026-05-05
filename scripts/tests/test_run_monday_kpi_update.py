"""Session 3.5 tests — CLI wrapper for /monday-kpi-update.

Covers:
  1. Argparse defaults align with Phase 11 verify protocol.
  2. _resolve_sa_key precedence: CLI flag > env var > DEFAULT_SA_KEY.
  3. _build_google_clients constructs only the services requested.
  4. main() returns 2 on missing leadership doc id or service account.
  5. main() threads CLI kwargs through to monday_kpi_update.main correctly.
"""
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Add scripts/ to path (the wrapper does this itself when invoked, but tests
# might import it before that path injection runs)
_SCRIPTS_DIR = Path(__file__).resolve().parent.parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import run_monday_kpi_update as wrapper


# ----- argparse ------------------------------------------------------------ #


def test_parse_args_defaults_match_phase_11_verify():
    args = wrapper._parse_args([])
    assert args.skip_deck is False
    assert args.skip_slack is False
    assert args.include_leadership_doc is False
    assert args.leadership_doc_id is None
    assert args.slack_channel is None
    assert args.deck_id == wrapper.DEFAULT_DECK_ID
    assert args.service_account is None  # falls through to env / default


def test_parse_args_accepts_skip_flags():
    args = wrapper._parse_args(["--skip-deck", "--skip-slack"])
    assert args.skip_deck is True
    assert args.skip_slack is True


def test_parse_args_accepts_leadership_doc_options():
    args = wrapper._parse_args(
        ["--include-leadership-doc", "--leadership-doc-id", "DOC_ABC"]
    )
    assert args.include_leadership_doc is True
    assert args.leadership_doc_id == "DOC_ABC"


def test_parse_args_accepts_channel_override():
    args = wrapper._parse_args(["--slack-channel", "C0TEST123"])
    assert args.slack_channel == "C0TEST123"


# ----- _resolve_sa_key precedence ------------------------------------------ #


def test_resolve_sa_key_prefers_cli_value(monkeypatch):
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", "/from/env.json")
    assert wrapper._resolve_sa_key("/from/cli.json") == "/from/cli.json"


def test_resolve_sa_key_falls_back_to_env(monkeypatch):
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", "/from/env.json")
    assert wrapper._resolve_sa_key(None) == "/from/env.json"


def test_resolve_sa_key_falls_back_to_default(monkeypatch):
    monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
    assert wrapper._resolve_sa_key(None) == wrapper.DEFAULT_SA_KEY


# ----- _build_google_clients lazy loading --------------------------------- #


def test_build_google_clients_returns_empty_when_neither_requested():
    """No imports of google.* libraries when caller wants no Google services."""
    services = wrapper._build_google_clients(
        "/fake/path.json", want_slides=False, want_docs=False
    )
    assert services == {}


def test_build_google_clients_constructs_only_requested(monkeypatch):
    """Slides only → docs absent. Docs only → slides absent."""
    fake_creds = MagicMock()
    fake_slides = MagicMock(name="slides")
    fake_docs = MagicMock(name="docs")

    fake_sa_module = MagicMock()
    fake_sa_module.Credentials.from_service_account_file.return_value = fake_creds

    def fake_build(name, version, credentials, cache_discovery):
        if name == "slides":
            return fake_slides
        if name == "docs":
            return fake_docs
        raise AssertionError(f"unexpected service: {name}")

    monkeypatch.setitem(
        sys.modules,
        "google.oauth2",
        MagicMock(service_account=fake_sa_module),
    )
    monkeypatch.setitem(
        sys.modules,
        "googleapiclient",
        MagicMock(),
    )
    monkeypatch.setitem(
        sys.modules,
        "googleapiclient.discovery",
        MagicMock(build=fake_build),
    )

    services_slides_only = wrapper._build_google_clients(
        "/fake/path.json", want_slides=True, want_docs=False
    )
    assert "slides" in services_slides_only
    assert "docs" not in services_slides_only

    services_docs_only = wrapper._build_google_clients(
        "/fake/path.json", want_slides=False, want_docs=True
    )
    assert "slides" not in services_docs_only
    assert "docs" in services_docs_only


# ----- main() error handling ---------------------------------------------- #


def test_main_returns_2_when_leadership_doc_id_missing(capsys):
    """--include-leadership-doc without --leadership-doc-id is a CLI error."""
    rc = wrapper.main(["--include-leadership-doc"])
    assert rc == 2
    err = capsys.readouterr().err
    assert "leadership-doc-id" in err.lower()


def test_main_returns_2_when_service_account_path_missing(monkeypatch, capsys):
    monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
    monkeypatch.setattr(wrapper, "DEFAULT_SA_KEY", "/definitely/does/not/exist.json")
    rc = wrapper.main(["--skip-deck", "--skip-slack"])
    assert rc == 2
    err = capsys.readouterr().err
    assert "service account key not found" in err.lower()


# ----- main() kwargs threading -------------------------------------------- #


def test_main_threads_skip_flags_into_monday_kpi_update(monkeypatch, tmp_path):
    """All CLI flags must surface on the call into monday_kpi_update.main."""
    fake_sa = tmp_path / "fake-sa.json"
    fake_sa.write_text("{}")

    monkeypatch.setattr(
        wrapper,
        "_build_google_clients",
        lambda sa_key_path, want_slides, want_docs: {},
    )

    captured_kwargs = {}

    def fake_main(**kwargs):
        captured_kwargs.update(kwargs)
        return {}

    fake_module = MagicMock()
    fake_module.main = fake_main

    class _PreflightError(Exception):
        pass

    fake_module.PreflightError = _PreflightError
    monkeypatch.setitem(sys.modules, "monday_kpi_update", fake_module)

    rc = wrapper.main(
        [
            "--skip-deck",
            "--skip-slack",
            "--service-account",
            str(fake_sa),
        ]
    )

    assert rc == 0
    assert captured_kwargs["skip_deck"] is True
    assert captured_kwargs["skip_slack"] is True
    assert captured_kwargs["include_leadership_doc"] is False
    assert captured_kwargs["fetch_presentation"] is None
    assert captured_kwargs["fetch_table_row_count"] is None
    assert captured_kwargs["slides_service"] is None
    assert captured_kwargs["docs_service"] is None


def test_main_threads_slack_channel_override(monkeypatch, tmp_path):
    fake_sa = tmp_path / "fake-sa.json"
    fake_sa.write_text("{}")

    monkeypatch.setattr(
        wrapper,
        "_build_google_clients",
        lambda sa_key_path, want_slides, want_docs: {},
    )

    captured = {}

    def fake_main(**kwargs):
        captured.update(kwargs)
        return {}

    fake_module = MagicMock()
    fake_module.main = fake_main
    fake_module.PreflightError = type("_PE", (Exception,), {})
    monkeypatch.setitem(sys.modules, "monday_kpi_update", fake_module)

    wrapper.main(
        [
            "--skip-deck",
            "--skip-slack",
            "--slack-channel",
            "C0OVERRIDE",
            "--service-account",
            str(fake_sa),
        ]
    )

    assert captured["slack_channel"] == "C0OVERRIDE"


def test_main_threads_slides_service_when_deck_enabled(monkeypatch, tmp_path):
    """skip_deck=False → fetch_presentation + fetch_table_row_count + slides_service
    are all threaded as truthy callables / mock object."""
    fake_sa = tmp_path / "fake-sa.json"
    fake_sa.write_text("{}")

    fake_slides = MagicMock(name="slides_service")
    monkeypatch.setattr(
        wrapper,
        "_build_google_clients",
        lambda sa_key_path, want_slides, want_docs: (
            {"slides": fake_slides} if want_slides else {}
        ),
    )

    captured = {}

    def fake_main(**kwargs):
        captured.update(kwargs)
        return {}

    fake_module = MagicMock()
    fake_module.main = fake_main
    fake_module.PreflightError = type("_PE", (Exception,), {})
    monkeypatch.setitem(sys.modules, "monday_kpi_update", fake_module)

    wrapper.main(
        [
            "--skip-slack",  # don't skip deck
            "--service-account",
            str(fake_sa),
        ]
    )

    assert captured["slides_service"] is fake_slides
    assert callable(captured["fetch_presentation"])
    assert callable(captured["fetch_table_row_count"])
