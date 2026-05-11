"""CLI entry point for /monday-kpi-update slash command.

Wires together the operational concerns that the contract layer (main()) doesn't
own:
  - Service-account credential loading (Slides, Docs, BigQuery, Firestore)
  - Google API client construction (slides_service, docs_service)
  - fetch_presentation + fetch_table_row_count callable construction
  - argparse + sane defaults aligned with Phase 11 verify protocol

Usage:

    # Phase 11 verify (Week 1): post to test channel, no deck, no leadership doc
    python scripts/run_monday_kpi_update.py --skip-deck

    # Fully dry — no surface writes (preflight + sensitivity gate only)
    python scripts/run_monday_kpi_update.py --skip-deck --skip-slack

    # Full run (deck + Slack + leadership doc on the May 13 tab)
    python scripts/run_monday_kpi_update.py \\
        --include-leadership-doc \\
        --leadership-doc-id 1DGHFBjXsfb1kb438QRPH9QZlG9fE2CzBs1WPtDP0AAU

    # Override channel for a one-off (e.g., post to #kpi-test instead of default)
    python scripts/run_monday_kpi_update.py --slack-channel C12345678

Required env vars:
    GOOGLE_APPLICATION_CREDENTIALS  path to service account JSON for BigQuery +
                                    Firestore (ADC-style auth). Defaults to
                                    /Users/deucethevenowworkm1/.config/bigquery-mcp-key.json
                                    if not set.
    SLACK_BOT_TOKEN                 Slack bot token with chat:write on the
                                    target channel (only required if not
                                    --skip-slack).
    SLACK_USER_ID_DEUCE             Slack user IDs for failure-alert mentions.
    SLACK_USER_ID_LEO               Optional; falls back to <!here> if unset.

Phase 11 channel routing:
    Default channel is the VERIFY channel (#kpi-dashboard-notifications) for
    Week 1 parallel-verify Mondays. After 2 clean Mondays prove parity, the
    cut-over is a one-line edit in monday_kpi_update.py to point the default
    at the PROD channel (#recess-goals-kpis).
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any, Callable, Dict, Optional

# Add scripts/ to sys.path so `import monday_kpi_update` and `from lib.* import`
# resolve when invoked as `python scripts/run_monday_kpi_update.py`.
_SCRIPTS_DIR = str(Path(__file__).resolve().parent)
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

DEFAULT_DECK_ID = "1kjg1ObSO1l15_R82w6hgQNOz8YYk3oUXPllBs-eGhow"
DEFAULT_SA_KEY = "/Users/deucethevenowworkm1/.config/bigquery-mcp-key.json"

# Minimum scopes required by each surface. Loaded only for surfaces actually
# used so a slack-only run doesn't need Slides/Docs grants.
SLIDES_SCOPES = [
    "https://www.googleapis.com/auth/presentations",
    "https://www.googleapis.com/auth/drive",
]
DOCS_SCOPES = [
    "https://www.googleapis.com/auth/documents",
]


def _resolve_sa_key(cli_value: Optional[str]) -> str:
    """Pick the service-account key path from CLI > env > default."""
    if cli_value:
        return cli_value
    env_value = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    if env_value:
        return env_value
    return DEFAULT_SA_KEY


def _build_google_clients(
    sa_key_path: str,
    *,
    want_slides: bool,
    want_docs: bool,
) -> Dict[str, Any]:
    """Construct Slides + Docs API clients lazily.

    Imports `google.oauth2` and `googleapiclient` inside the function so a
    `--skip-deck --skip-slack` (or import-test) caller doesn't need them
    installed. Returns a dict keyed by service name; missing keys mean
    "not requested."
    """
    if not (want_slides or want_docs):
        return {}

    from google.oauth2 import service_account  # type: ignore
    from googleapiclient.discovery import build  # type: ignore

    scopes = []
    if want_slides:
        scopes.extend(SLIDES_SCOPES)
    if want_docs:
        scopes.extend(DOCS_SCOPES)

    creds = service_account.Credentials.from_service_account_file(
        sa_key_path, scopes=scopes
    )

    services: Dict[str, Any] = {}
    if want_slides:
        services["slides"] = build(
            "slides", "v1", credentials=creds, cache_discovery=False
        )
    if want_docs:
        services["docs"] = build(
            "docs", "v1", credentials=creds, cache_discovery=False
        )
    return services


def _build_fetch_presentation(slides_service: Any) -> Callable[[str], Dict[str, Any]]:
    """Closure that fetches a presentation by deck_id via the Slides API."""
    def fetcher(deck_id: str) -> Dict[str, Any]:
        return slides_service.presentations().get(presentationId=deck_id).execute()
    return fetcher


def _parse_args(argv: Optional[list] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="run_monday_kpi_update",
        description="Run /monday-kpi-update slash command with real Google API clients.",
    )
    parser.add_argument(
        "--skip-deck",
        action="store_true",
        help="Skip Slides API deck writing (default: False). Use this when "
             "running before manual slide prep is complete.",
    )
    parser.add_argument(
        "--skip-rocks-deck",
        action="store_true",
        help="Skip rocks/projects deck slides (default: False — rocks "
             "deck is included). Use this when the rocks slides "
             "(<Dept> · Auto-Updated Rocks & Projects) haven't been "
             "added to the deck yet. Scorecard slides still write.",
    )
    parser.add_argument(
        "--skip-slack",
        action="store_true",
        help="Skip Slack post (default: False). Useful for dry runs.",
    )
    parser.add_argument(
        "--include-leadership-doc",
        action="store_true",
        help="Write rendered pulse to the leadership Google Doc (default: False). "
             "Requires --leadership-doc-id and that the doc has the sentinel pair "
             "<<KPI_LEADERSHIP_START>><<KPI_LEADERSHIP_END>> as plain unstyled text.",
    )
    parser.add_argument(
        "--leadership-doc-id",
        type=str,
        default=None,
        help="Google Doc ID to write the leadership section into.",
    )
    parser.add_argument(
        "--slack-channel",
        type=str,
        default=None,
        help="Slack channel ID. Defaults to monday_kpi_update.DEFAULT_SLACK_CHANNEL "
             "(VERIFY channel #kpi-dashboard-notifications during Phase 11).",
    )
    parser.add_argument(
        "--deck-id",
        type=str,
        default=DEFAULT_DECK_ID,
        help=f"Slides deck ID (default: {DEFAULT_DECK_ID}).",
    )
    parser.add_argument(
        "--service-account",
        type=str,
        default=None,
        help="Path to GCP service account JSON. Falls back to "
             "$GOOGLE_APPLICATION_CREDENTIALS, then to "
             f"{DEFAULT_SA_KEY}.",
    )
    return parser.parse_args(argv)


def main(argv: Optional[list] = None) -> int:
    args = _parse_args(argv)

    if args.include_leadership_doc and not args.leadership_doc_id:
        print(
            "ERROR: --include-leadership-doc requires --leadership-doc-id",
            file=sys.stderr,
        )
        return 2

    sa_key = _resolve_sa_key(args.service_account)
    if not Path(sa_key).exists():
        print(
            f"ERROR: service account key not found at {sa_key}. "
            "Set --service-account or $GOOGLE_APPLICATION_CREDENTIALS.",
            file=sys.stderr,
        )
        return 2

    # Surface BigQuery + Firestore creds via the same env var the dashboard
    # already uses. Setting it here is idempotent.
    os.environ.setdefault("GOOGLE_APPLICATION_CREDENTIALS", sa_key)

    services = _build_google_clients(
        sa_key,
        want_slides=not args.skip_deck,
        want_docs=args.include_leadership_doc,
    )

    slides_service = services.get("slides")
    docs_service = services.get("docs")

    fetch_presentation = None
    fetch_table_row_count = None
    if slides_service is not None:
        from lib.deck_writer import build_table_row_count_fetcher  # noqa: E402

        fetch_presentation = _build_fetch_presentation(slides_service)
        fetch_table_row_count = build_table_row_count_fetcher(slides_service)

    # Lazy import so sys.path is set first
    import monday_kpi_update  # noqa: E402

    kwargs: Dict[str, Any] = {
        "deck_id": args.deck_id,
        "skip_deck": args.skip_deck,
        "skip_rocks_deck": args.skip_rocks_deck,
        "skip_slack": args.skip_slack,
        "include_leadership_doc": args.include_leadership_doc,
        "leadership_doc_id": args.leadership_doc_id,
        "fetch_presentation": fetch_presentation,
        "fetch_table_row_count": fetch_table_row_count,
        "slides_service": slides_service,
        "docs_service": docs_service,
    }
    if args.slack_channel:
        kwargs["slack_channel"] = args.slack_channel

    try:
        rendered = monday_kpi_update.main(**kwargs)
    except monday_kpi_update.PreflightError as e:
        print(f"\nPre-flight failed:\n{e}", file=sys.stderr)
        return 2
    except SystemExit:
        # Sensitivity gate aborted via SystemExit. Re-raise so exit code propagates.
        raise

    total_rows = sum(len(p.get("scorecard_rows", [])) for p in rendered.values())
    print(
        f"\nDone — rendered {total_rows} rows across {len(rendered)} depts. "
        f"Surfaces: deck={'skipped' if args.skip_deck else 'wrote'}, "
        f"slack={'skipped' if args.skip_slack else 'posted'}, "
        f"leadership-doc={'wrote' if args.include_leadership_doc else 'skipped'}."
    )
    return 0


if __name__ == "__main__":  # pragma: no cover — manual invocation only
    sys.exit(main())
