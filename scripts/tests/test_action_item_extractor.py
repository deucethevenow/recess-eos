"""Tests for ActionItemExtractor — Phase 4 Task 2 (Rock 007).

Covers:
1. Empty/whitespace transcript short-circuits to [] (no API call)
2. ActionItem dataclass / Pydantic schema validates required fields
3. extract() calls messages.parse() with the right model + schema
4. extract() unpacks parsed_output into ActionItem list
5. extract() handles None parsed_output (refusal / parse failure) gracefully
6. Live integration test against real transcript pulled from Airtable
"""
from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest

from lib.action_item_extractor import (
    ActionItem,
    ActionItemExtractionError,
    ActionItemExtractor,
    ActionItemList,
)


# ---------- Schema ----------


class TestActionItemSchema:
    def test_required_fields_validated(self):
        # owner, action, source_quote required; due_date optional
        item = ActionItem(
            owner="danny@recess.is",
            action="Follow up with Walmart",
            source_quote="I'll reach out to Walmart by Friday",
        )
        assert item.due_date is None

    def test_due_date_optional(self):
        item = ActionItem(
            owner="char@recess.is",
            action="Review proposal",
            due_date="2026-04-30",
            source_quote="I'll have it by month-end",
        )
        assert item.due_date == "2026-04-30"

    def test_action_item_list_wraps_items(self):
        wrapped = ActionItemList(items=[
            ActionItem(owner="a", action="b", source_quote="c"),
        ])
        assert len(wrapped.items) == 1


# ---------- Empty / short-circuit paths ----------


class TestEmptyTranscriptShortCircuit:
    def test_empty_string_returns_empty_list_no_api_call(self):
        mock_client = MagicMock()
        extractor = ActionItemExtractor(client=mock_client)
        assert extractor.extract("") == []
        mock_client.messages.parse.assert_not_called()

    def test_whitespace_only_returns_empty_list(self):
        mock_client = MagicMock()
        extractor = ActionItemExtractor(client=mock_client)
        assert extractor.extract("   \n\t  \n") == []
        mock_client.messages.parse.assert_not_called()


# ---------- Mocked extraction ----------


def _mock_parse_response(items: list[dict] | None):
    """Build a mock response from `client.messages.parse()`."""
    response = MagicMock()
    if items is None:
        response.parsed_output = None
    else:
        response.parsed_output = ActionItemList(
            items=[ActionItem(**i) for i in items]
        )
    return response


class TestExtraction:
    def test_default_model_is_opus_4_7(self):
        # User chose Opus 4.7 default after a 2026-04-27 verification test
        # showed it catches ~83% more action items than Sonnet 4.6 on real
        # Recess transcripts. Accuracy > cost at this call volume.
        mock_client = MagicMock()
        mock_client.messages.parse.return_value = _mock_parse_response([])

        extractor = ActionItemExtractor(client=mock_client)
        extractor.extract("Some real transcript text", meeting_title="Sales L10")

        call_kwargs = mock_client.messages.parse.call_args[1]
        assert call_kwargs["model"] == "claude-opus-4-7"
        # output_format is the Pydantic schema, not raw JSON schema
        assert call_kwargs["output_format"] is ActionItemList
        # System prompt mentions the extraction task
        system = call_kwargs["system"]
        system_text = system if isinstance(system, str) else system[0]["text"]
        assert "action item" in system_text.lower()

    def test_model_is_overridable_via_constructor(self):
        # Escape hatch: callers can flip to Sonnet 4.6 per-instance for
        # high-volume / low-stakes batch work where cost matters more.
        mock_client = MagicMock()
        mock_client.messages.parse.return_value = _mock_parse_response([])

        extractor = ActionItemExtractor(client=mock_client, model="claude-sonnet-4-6")
        extractor.extract("transcript", meeting_title="L10")

        assert mock_client.messages.parse.call_args[1]["model"] == "claude-sonnet-4-6"

    def test_passes_transcript_and_title_in_user_message(self):
        mock_client = MagicMock()
        mock_client.messages.parse.return_value = _mock_parse_response([])

        extractor = ActionItemExtractor(client=mock_client)
        extractor.extract(
            "Danny will follow up.",
            meeting_title="Sales L10 — Apr 21",
        )

        user_msg = mock_client.messages.parse.call_args[1]["messages"][0]
        assert user_msg["role"] == "user"
        # Both the title and transcript content must reach the model
        assert "Sales L10 — Apr 21" in user_msg["content"]
        assert "Danny will follow up." in user_msg["content"]

    def test_returns_parsed_action_items(self):
        mock_client = MagicMock()
        mock_client.messages.parse.return_value = _mock_parse_response([
            {
                "owner": "danny@recess.is",
                "action": "Follow up with Walmart on Q3 RFP",
                "due_date": "2026-04-30",
                "source_quote": "I'll get back to Walmart by month end",
            },
            {
                "owner": "char@recess.is",
                "action": "Send Q2 retention report to Andy",
                "due_date": None,
                "source_quote": "I'll send it over after this call",
            },
        ])

        extractor = ActionItemExtractor(client=mock_client)
        items = extractor.extract("transcript", meeting_title="L10")

        assert len(items) == 2
        assert items[0].owner == "danny@recess.is"
        assert items[0].action == "Follow up with Walmart on Q3 RFP"
        assert items[0].due_date == "2026-04-30"
        assert items[1].due_date is None

    def test_none_parsed_output_returns_empty_list(self):
        # Refusal or parse failure should not crash callers
        mock_client = MagicMock()
        mock_client.messages.parse.return_value = _mock_parse_response(None)

        extractor = ActionItemExtractor(client=mock_client)
        assert extractor.extract("transcript", meeting_title="L10") == []

    def test_no_anthropic_client_provided_uses_default(self):
        # Constructing with no client should fall back to anthropic.Anthropic()
        # (which reads ANTHROPIC_API_KEY from env). We patch the module-level
        # constructor to avoid making a real API call.
        with patch("lib.action_item_extractor.anthropic.Anthropic") as mock_ctor:
            ActionItemExtractor()
            mock_ctor.assert_called_once()

    def test_anthropic_api_error_wrapped_in_extraction_error(self):
        # Per repo convention (AirtableAPIError, AsanaAuthError), SDK errors
        # are wrapped so callers don't import anthropic. The original error
        # is preserved as __cause__.
        import anthropic

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_response.headers = {"retry-after": "60"}
        original_error = anthropic.RateLimitError(
            message="rate limited",
            response=mock_response,
            body=None,
        )
        mock_client.messages.parse.side_effect = original_error

        extractor = ActionItemExtractor(client=mock_client)
        with pytest.raises(ActionItemExtractionError) as exc_info:
            extractor.extract("transcript", meeting_title="L10")

        # Wrapped exception preserves the original SDK error for diagnosis
        assert exc_info.value.__cause__ is original_error


# ---------- Live integration test ----------
#
# Hits real Anthropic API + real Airtable. Skipped without env. Tagged
# @pytest.mark.integration so default test runs don't burn tokens.


_LIVE_ENV_PRESENT = all(
    os.environ.get(var)
    for var in (
        "ANTHROPIC_API_KEY",
        "AIRTABLE_API_KEY",
        "AIRTABLE_BASE_ID",
        "AIRTABLE_TABLE_NAME",
    )
)


@pytest.mark.integration
@pytest.mark.skipif(
    not _LIVE_ENV_PRESENT,
    reason="ANTHROPIC_API_KEY + AIRTABLE_* required for live extraction test",
)
class TestLiveExtraction:
    def test_extracts_real_action_items_from_real_transcript(self):
        """Pull a real Deuce/Char 1:1, run extraction, validate shape."""
        from lib.airtable_client import AirtableClient

        airtable = AirtableClient()
        results = airtable.find_transcripts(
            participant_email="deuce@recess.is",
            title="Deuce/Char Weekly",
            since_days=30,
            limit=1,
        )
        assert len(results) >= 1, "No recent Deuce/Char 1:1 found in Airtable"
        transcript = results[0]["transcript"]
        title = results[0]["title"]

        extractor = ActionItemExtractor()
        items = extractor.extract(transcript, meeting_title=title)

        # Must return a list with ≥1 item (real Deuce/Char weekly 1:1
        # reliably produces commitments — manual run extracted 7).
        assert isinstance(items, list)
        assert len(items) >= 1, "Expected at least one action item from a real 1:1"

        # Normalize whitespace once for substring checks (transcripts have
        # \r\n, double spaces, etc. that an exact substring match would miss).
        normalized_transcript = " ".join(transcript.split()).lower()

        for item in items:
            assert isinstance(item, ActionItem)
            assert item.owner
            assert item.action
            assert item.source_quote
            assert len(item.source_quote) <= 200, "Source quote should be short"
            # Grounding check: the quote must actually appear in the
            # transcript. The system prompt explicitly forbids paraphrase.
            normalized_quote = " ".join(item.source_quote.split()).lower()
            assert normalized_quote in normalized_transcript, (
                f"source_quote {item.source_quote!r} not found in transcript "
                f"(checked with whitespace-normalized substring match)"
            )
