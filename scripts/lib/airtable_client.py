"""Airtable client for Recess OS — Phase 4 (Rock 007) meeting transcript pulls.

Pulls Fireflies-Call transcripts from the Airtable base populated by Make.com.
Used by ceos-meeting-prep + /meeting-wrap to surface "the most recent
<dept> meeting where <facilitator> participated".

Auth: AIRTABLE_API_KEY / AIRTABLE_BASE_ID / AIRTABLE_TABLE_NAME env vars.
Source these from ~/Projects/daily-brief-agent/.env before invoking.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import requests


# Connect timeout, read timeout. Read is generous because transcript fields
# can be hundreds of KB.
REQUEST_TIMEOUT = (10, 60)


class AirtableAuthError(Exception):
    """Raised when required Airtable env vars are missing."""


class AirtableAPIError(Exception):
    """Raised when an Airtable HTTP call fails."""


def _escape_formula_string(value: str) -> str:
    """Escape single quotes for safe inclusion in an Airtable formula literal.

    Airtable's formula language uses ``\\'`` to embed a literal single quote
    inside a single-quoted string. (The ``''`` doubling pattern from SQL is
    rejected as INVALID_FILTER_BY_FORMULA — verified live against the API.)

    Also escapes backslashes themselves so that an input like ``a\\b`` doesn't
    accidentally introduce an escape sequence.
    """
    return value.replace("\\", "\\\\").replace("'", "\\'")


def build_transcript_formula(
    participant_email: str,
    title_substring: Optional[str],
    since_iso: str,
) -> str:
    """Build an Airtable filterByFormula for Fireflies Call transcripts.

    Constraints:
    - Source Material = 'Fireflies Call' (excludes other ingest types)
    - Created date is after ``since_iso``
    - ``participant_email`` appears in either Participants or Host Name
    - If ``title_substring`` provided, Title contains it (case-insensitive,
      and guarded against null Title via ``AND({Title}, ...)``).

    Caller-provided strings (email, title) are escaped to prevent formula
    injection. ``since_iso`` is internally generated and assumed ISO-8601.
    """
    email = _escape_formula_string(participant_email)

    clauses = [
        "{Source Material}='Fireflies Call'",
        f"IS_AFTER({{Created}}, '{since_iso}')",
        (
            "OR("
            f"FIND('{email}', {{Participants}}), "
            f"FIND('{email}', {{Host Name}})"
            ")"
        ),
    ]

    if title_substring:
        title = _escape_formula_string(title_substring.lower())
        # AND({Title}, ...) short-circuits when Title is null (not all records have one)
        clauses.append(
            f"AND({{Title}}, FIND(LOWER('{title}'), LOWER({{Title}})))"
        )

    return "AND(" + ", ".join(clauses) + ")"


def _normalize_record(record: dict[str, Any]) -> dict[str, Any]:
    """Map Airtable field names to snake_case Python keys with safe defaults."""
    fields = record.get("fields", {})
    return {
        "id": record.get("id", ""),
        "title": fields.get("Title", ""),
        "created": fields.get("Created", ""),
        "participants": fields.get("Participants", ""),
        "host": fields.get("Host Name", ""),
        "transcript": fields.get("Text", ""),
        "summary": fields.get("Summary", ""),
        "meeting_type": fields.get("Meeting Type", ""),
        "duration_seconds": fields.get("Duration (in seconds)"),
    }


class AirtableClient:
    """Read-only Airtable client for Fireflies Call transcripts."""

    BASE_URL = "https://api.airtable.com/v0"

    def __init__(self) -> None:
        api_key = os.environ.get("AIRTABLE_API_KEY")
        base_id = os.environ.get("AIRTABLE_BASE_ID")
        table_name = os.environ.get("AIRTABLE_TABLE_NAME")

        missing = [
            name
            for name, value in (
                ("AIRTABLE_API_KEY", api_key),
                ("AIRTABLE_BASE_ID", base_id),
                ("AIRTABLE_TABLE_NAME", table_name),
            )
            if not value
        ]
        if missing:
            raise AirtableAuthError(
                f"Missing required env var(s): {', '.join(missing)}. "
                "Source from ~/Projects/daily-brief-agent/.env first."
            )

        self.api_key = api_key
        self.base_id = base_id
        self.table_name = table_name

    def find_transcripts(
        self,
        participant_email: str,
        *,
        title: Optional[str] = None,
        since_days: int = 30,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Pull Fireflies transcripts matching participant + title + recency.

        Args:
            participant_email: Email that must appear in Participants or Host Name.
            title: Case-insensitive substring filter on Title.
                If None, no title constraint applied.
            since_days: Only return records Created within the last N days.
            limit: Cap on records returned. Must be <= 100 (Airtable single-page
                limit). Pagination via ``offset`` is intentionally not implemented
                — the L10 use case wants the most recent meeting, not history.

        Returns:
            List of normalized transcript dicts sorted by Created desc.

        Raises:
            ValueError: If ``limit`` exceeds 100.
            AirtableAPIError: HTTP failure, malformed response, or network issue.
        """
        if limit > 100:
            raise ValueError(
                f"limit={limit} exceeds Airtable single-page max of 100. "
                "If you need more results, paginate with offset (not implemented)."
            )

        since_iso = (
            datetime.now(timezone.utc) - timedelta(days=since_days)
        ).strftime("%Y-%m-%d")

        formula = build_transcript_formula(
            participant_email=participant_email,
            title_substring=title,
            since_iso=since_iso,
        )

        url = f"{self.BASE_URL}/{self.base_id}/{self.table_name}"
        headers = {"Authorization": f"Bearer {self.api_key}"}
        params = {
            "filterByFormula": formula,
            "sort[0][field]": "Created",
            "sort[0][direction]": "desc",
            "maxRecords": limit,
        }

        try:
            response = requests.get(
                url, headers=headers, params=params, timeout=REQUEST_TIMEOUT
            )
        except requests.RequestException as exc:
            raise AirtableAPIError(f"Failed to reach Airtable: {exc}") from exc

        if response.status_code >= 400:
            raise AirtableAPIError(
                f"Airtable returned {response.status_code}: {response.text[:200]}"
            )

        try:
            data = response.json()
        except ValueError as exc:
            # Cloudflare 5xx, truncated body, or non-JSON error pages can land here
            raise AirtableAPIError(
                f"Airtable returned non-JSON response: {response.text[:200]}"
            ) from exc

        records = data.get("records", [])
        return [_normalize_record(rec) for rec in records]
