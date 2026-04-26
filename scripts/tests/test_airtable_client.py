"""Tests for AirtableClient — Phase 4 transcript pull (Rock 007).

Covers:
1. Auth error paths (missing env vars)
2. Pure formula construction with proper escaping
3. HTTP request shape (URL, headers, params)
4. Response normalization (Airtable fields → snake_case)
5. Error handling (HTTP errors, network errors)
"""
from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest
import requests

from lib.airtable_client import (
    AirtableAPIError,
    AirtableAuthError,
    AirtableClient,
    _escape_formula_string,
    build_transcript_formula,
)


# ---------- Pure helper: formula escaping ----------


class TestEscapeFormulaString:
    def test_no_special_chars_pass_through(self):
        assert _escape_formula_string("plain text") == "plain text"

    def test_single_quote_backslash_escaped(self):
        # Verified live: Airtable accepts \' as an embedded quote inside
        # single-quoted formula literals. The SQL-style '' doubling fails 422.
        assert _escape_formula_string("Danny's L10") == "Danny\\'s L10"

    def test_multiple_quotes_all_escaped(self):
        assert _escape_formula_string("'a'b'") == "\\'a\\'b\\'"

    def test_backslash_doubled(self):
        # If user input itself contains a backslash, it must be doubled before
        # the apostrophe replacement, otherwise we'd create an unintended
        # escape sequence.
        assert _escape_formula_string("a\\b") == "a\\\\b"

    def test_empty_string(self):
        assert _escape_formula_string("") == ""


# ---------- Pure helper: formula building ----------


class TestBuildTranscriptFormula:
    def test_participant_only_no_title(self):
        formula = build_transcript_formula(
            participant_email="danny@recess.is",
            title_substring=None,
            since_iso="2026-04-01",
        )
        # Must filter to Fireflies Calls only
        assert "{Source Material}='Fireflies Call'" in formula
        # Must filter by date
        assert "IS_AFTER({Created}, '2026-04-01')" in formula
        # Must search both Participants AND Host Name
        assert "FIND('danny@recess.is', {Participants})" in formula
        assert "FIND('danny@recess.is', {Host Name})" in formula
        # No title clause when None
        assert "Title" not in formula

    def test_with_title_substring_case_insensitive(self):
        formula = build_transcript_formula(
            participant_email="danny@recess.is",
            title_substring="Sales L10",
            since_iso="2026-04-01",
        )
        # Title substring must be lowercased on both sides for case-insensitive match
        assert "LOWER('sales l10')" in formula
        assert "LOWER({Title})" in formula
        # Must guard against null Title (AND short-circuits)
        assert "AND({Title}," in formula

    def test_apostrophe_in_title_escaped(self):
        # Critical: prevent formula injection via title input.
        # Verified live (/tmp/airtable_escape_probe.py): Airtable accepts \'
        # inside single-quoted literals; rejects '' doubling with HTTP 422.
        formula = build_transcript_formula(
            participant_email="danny@recess.is",
            title_substring="Danny's weekly",
            since_iso="2026-04-01",
        )
        # Single quote must be backslash-escaped
        assert "danny\\'s weekly" in formula
        # Must NOT contain a bare apostrophe that would terminate the literal
        assert "'danny's" not in formula

    def test_email_with_dot_and_plus_preserved(self):
        formula = build_transcript_formula(
            participant_email="user.name+tag@recess.is",
            title_substring=None,
            since_iso="2026-04-01",
        )
        assert "user.name+tag@recess.is" in formula

    def test_email_with_apostrophe_escaped(self):
        # RFC 5321 allows apostrophes in local-part. Same injection risk as title.
        formula = build_transcript_formula(
            participant_email="o'brien@recess.is",
            title_substring=None,
            since_iso="2026-04-01",
        )
        # Apostrophe in email must be backslash-escaped just like title
        assert "o\\'brien@recess.is" in formula
        # Must NOT contain unescaped form that would break the formula literal
        assert "'o'brien" not in formula


# ---------- Auth / construction ----------


class TestAirtableClientAuth:
    def test_raises_when_api_key_missing(self, monkeypatch):
        monkeypatch.delenv("AIRTABLE_API_KEY", raising=False)
        monkeypatch.setenv("AIRTABLE_BASE_ID", "base")
        monkeypatch.setenv("AIRTABLE_TABLE_NAME", "table")
        with pytest.raises(AirtableAuthError, match="AIRTABLE_API_KEY"):
            AirtableClient()

    def test_raises_when_base_id_missing(self, monkeypatch):
        monkeypatch.setenv("AIRTABLE_API_KEY", "key")
        monkeypatch.delenv("AIRTABLE_BASE_ID", raising=False)
        monkeypatch.setenv("AIRTABLE_TABLE_NAME", "table")
        with pytest.raises(AirtableAuthError, match="AIRTABLE_BASE_ID"):
            AirtableClient()

    def test_raises_when_table_name_missing(self, monkeypatch):
        monkeypatch.setenv("AIRTABLE_API_KEY", "key")
        monkeypatch.setenv("AIRTABLE_BASE_ID", "base")
        monkeypatch.delenv("AIRTABLE_TABLE_NAME", raising=False)
        with pytest.raises(AirtableAuthError, match="AIRTABLE_TABLE_NAME"):
            AirtableClient()

    def test_initializes_when_all_env_present(self, monkeypatch):
        monkeypatch.setenv("AIRTABLE_API_KEY", "key")
        monkeypatch.setenv("AIRTABLE_BASE_ID", "base")
        monkeypatch.setenv("AIRTABLE_TABLE_NAME", "table")
        client = AirtableClient()
        assert client.api_key == "key"
        assert client.base_id == "base"
        assert client.table_name == "table"


# ---------- HTTP shape ----------


@pytest.fixture
def airtable_env(monkeypatch):
    monkeypatch.setenv("AIRTABLE_API_KEY", "test-key-123")
    monkeypatch.setenv("AIRTABLE_BASE_ID", "appTEST")
    monkeypatch.setenv("AIRTABLE_TABLE_NAME", "Meetings")


def _mock_response(records: list[dict], status: int = 200):
    """Build a mock requests.Response."""
    resp = MagicMock(spec=requests.Response)
    resp.status_code = status
    resp.json.return_value = {"records": records}
    resp.raise_for_status = MagicMock()
    if status >= 400:
        resp.raise_for_status.side_effect = requests.HTTPError(f"{status} error")
    return resp


class TestGetTranscriptsHTTP:
    def test_calls_correct_url_and_auth_header(self, airtable_env):
        client = AirtableClient()
        with patch("lib.airtable_client.requests.get") as mock_get:
            mock_get.return_value = _mock_response([])
            client.find_transcripts(
                participant_email="danny@recess.is",
            )

        call_args = mock_get.call_args
        assert call_args[0][0] == "https://api.airtable.com/v0/appTEST/Meetings"
        assert call_args[1]["headers"]["Authorization"] == "Bearer test-key-123"

    def test_passes_formula_and_sort_and_max_records(self, airtable_env):
        client = AirtableClient()
        with patch("lib.airtable_client.requests.get") as mock_get:
            mock_get.return_value = _mock_response([])
            client.find_transcripts(
                participant_email="danny@recess.is",
                title="L10",
                since_days=14,
                limit=5,
            )

        params = mock_get.call_args[1]["params"]
        # filterByFormula must be present and contain key constraints
        assert "filterByFormula" in params
        assert "{Source Material}='Fireflies Call'" in params["filterByFormula"]
        # Sort by Created desc — Airtable uses sort[0][field]/[direction] form
        assert params.get("sort[0][field]") == "Created"
        assert params.get("sort[0][direction]") == "desc"
        # maxRecords forwarded
        assert params.get("maxRecords") == 5

    def test_returns_normalized_records(self, airtable_env):
        sample = [
            {
                "id": "rec123",
                "fields": {
                    "Title": "Sales L10 — 2026-04-21",
                    "Created": "2026-04-21T15:00:00.000Z",
                    "Participants": "danny@recess.is,andy@recess.is",
                    "Host Name": "danny@recess.is",
                    "Text": "Full transcript text here",
                    "Summary": "Discussed pipeline coverage",
                    "Meeting Type": "Internal",
                    "Duration (in seconds)": 1800,
                },
            }
        ]
        client = AirtableClient()
        with patch("lib.airtable_client.requests.get") as mock_get:
            mock_get.return_value = _mock_response(sample)
            results = client.find_transcripts(
                participant_email="danny@recess.is",
            )

        assert len(results) == 1
        rec = results[0]
        assert rec["id"] == "rec123"
        assert rec["title"] == "Sales L10 — 2026-04-21"
        assert rec["created"] == "2026-04-21T15:00:00.000Z"
        assert rec["participants"] == "danny@recess.is,andy@recess.is"
        assert rec["host"] == "danny@recess.is"
        assert rec["transcript"] == "Full transcript text here"
        assert rec["summary"] == "Discussed pipeline coverage"
        assert rec["meeting_type"] == "Internal"
        assert rec["duration_seconds"] == 1800

    def test_missing_optional_fields_default_to_none_or_empty(self, airtable_env):
        sample = [
            {
                "id": "rec456",
                "fields": {
                    "Created": "2026-04-21T15:00:00.000Z",
                    # No Title, no Text, no Summary, no Participants, no Host Name
                },
            }
        ]
        client = AirtableClient()
        with patch("lib.airtable_client.requests.get") as mock_get:
            mock_get.return_value = _mock_response(sample)
            results = client.find_transcripts(
                participant_email="danny@recess.is",
            )

        rec = results[0]
        assert rec["title"] == ""
        assert rec["transcript"] == ""
        assert rec["summary"] == ""
        assert rec["participants"] == ""
        assert rec["host"] == ""
        assert rec["duration_seconds"] is None

    def test_empty_result_returns_empty_list(self, airtable_env):
        client = AirtableClient()
        with patch("lib.airtable_client.requests.get") as mock_get:
            mock_get.return_value = _mock_response([])
            results = client.find_transcripts(
                participant_email="danny@recess.is",
            )
        assert results == []


# ---------- Error handling ----------


class TestErrorHandling:
    def test_http_error_raises_airtable_api_error(self, airtable_env):
        client = AirtableClient()
        with patch("lib.airtable_client.requests.get") as mock_get:
            mock_get.return_value = _mock_response([], status=403)
            with pytest.raises(AirtableAPIError, match="403"):
                client.find_transcripts(
                    participant_email="danny@recess.is",
                )

    def test_network_error_raises_airtable_api_error(self, airtable_env):
        client = AirtableClient()
        with patch("lib.airtable_client.requests.get") as mock_get:
            mock_get.side_effect = requests.ConnectionError("network down")
            with pytest.raises(AirtableAPIError, match="Failed to reach Airtable"):
                client.find_transcripts(
                    participant_email="danny@recess.is",
                )

    def test_timeout_set_on_request(self, airtable_env):
        """Must always pass a timeout to prevent hanging cron jobs."""
        client = AirtableClient()
        with patch("lib.airtable_client.requests.get") as mock_get:
            mock_get.return_value = _mock_response([])
            client.find_transcripts(
                participant_email="danny@recess.is",
            )
        assert mock_get.call_args[1].get("timeout") is not None

    def test_malformed_json_response_raises_airtable_api_error(self, airtable_env):
        """200 status with non-JSON body (e.g., Cloudflare HTML error page)."""
        client = AirtableClient()
        bad_response = MagicMock(spec=requests.Response)
        bad_response.status_code = 200
        bad_response.json.side_effect = ValueError("Expecting value: line 1 column 1")
        bad_response.text = "<html>Cloudflare error</html>"

        with patch("lib.airtable_client.requests.get") as mock_get:
            mock_get.return_value = bad_response
            with pytest.raises(AirtableAPIError, match="non-JSON"):
                client.find_transcripts(participant_email="danny@recess.is")


# ---------- Input validation ----------


class TestInputValidation:
    def test_limit_over_100_raises_value_error(self, airtable_env):
        """Airtable returns max 100 records per page; we don't paginate."""
        client = AirtableClient()
        with pytest.raises(ValueError, match="exceeds Airtable single-page max of 100"):
            client.find_transcripts(
                participant_email="danny@recess.is",
                limit=500,
            )

    def test_limit_exactly_100_is_allowed(self, airtable_env):
        """Boundary: limit=100 is the max allowed page size."""
        client = AirtableClient()
        with patch("lib.airtable_client.requests.get") as mock_get:
            mock_get.return_value = _mock_response([])
            # Should NOT raise
            client.find_transcripts(
                participant_email="danny@recess.is",
                limit=100,
            )


# ---------- Live integration test ----------
#
# Runs against the real Airtable base when credentials are present in env.
# Skipped in CI / on machines without daily-brief-agent/.env sourced.
# This is the test that catches "formula syntax compiles in Python but Airtable
# rejects it with 422" — exactly the class of bug that slipped past the
# mocked unit tests during initial development of this module.


_LIVE_ENV_PRESENT = all(
    os.environ.get(var)
    for var in ("AIRTABLE_API_KEY", "AIRTABLE_BASE_ID", "AIRTABLE_TABLE_NAME")
)


@pytest.mark.integration
@pytest.mark.skipif(
    not _LIVE_ENV_PRESENT,
    reason="AIRTABLE_* env vars not set — source from daily-brief-agent/.env",
)
class TestLiveAirtable:
    def test_apostrophe_substring_does_not_400(self):
        """Regression guard: title with apostrophe must not produce a 422.

        We don't care about the result count — only that Airtable parses the
        formula. Picks a phrase that genuinely won't match anything so the
        test is fast.
        """
        client = AirtableClient()
        # Should NOT raise AirtableAPIError("422 ...")
        results = client.find_transcripts(
            participant_email="deuce@recess.is",
            title="don't exist nowhere xyzqq",
            since_days=7,
            limit=1,
        )
        assert results == []

    def test_basic_pull_returns_records(self):
        """Smoke test: pull deuce's last 30d meetings without title filter."""
        client = AirtableClient()
        results = client.find_transcripts(
            participant_email="deuce@recess.is",
            since_days=30,
            limit=3,
        )
        # We expect Deuce to have at least one meeting in the last 30 days.
        # If this fails, either Airtable is empty or the query is wrong.
        assert len(results) >= 1
        # Records must be normalized to expected keys
        for r in results:
            assert set(r.keys()) >= {
                "id", "title", "created", "participants",
                "host", "transcript", "summary", "duration_seconds",
            }
