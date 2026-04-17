"""All-Hands Deck Updater — Google Slides consumer for bi-weekly metric updates.

Renders text replacements for metric placeholders in the all-hands slide deck.
Consumes MetricPayload objects built by the orchestrator — no BQ access,
no transforms, no formatting logic. Pure consumer.

Architecture:
    render_deck_updates()  →  pure render (SlideReplacement list)
    apply_deck_updates()   →  MCP I/O (Google Slides API via MCP)

Scope: Metric placeholders ONLY. Rock milestones deferred to Phase 3.
"""

import re
from dataclasses import dataclass
from typing import Optional

from lib.metric_payloads import MetricPayload, SENSITIVITY_LEVELS
from lib.orchestrator import ConsumerResult


DECK_ID = "1kjg1ObSO1l15_R82w6hgQNOz8YYk3oUXPllBs-eGhow"

DEPT_SLIDE_MAP: dict[str, int] = {
    "leadership": 28,
    "sales": 29,
    "demand_am": 30,
    "supply": 31,
    "supply_am": 32,
    "marketing": 33,
    "engineering": 34,
    "accounting": 35,
}


@dataclass(frozen=True)
class SlideReplacement:
    """A single text replacement operation for a slide."""
    placeholder: str      # "{{sales_pipeline_coverage}}"
    replacement: str      # "2.1x / 2.5x"
    dept_id: str
    metric_name: str
    registry_key: str     # for audit trail matching


class DeckStructureDriftError(Exception):
    """Raised when expected placeholders are missing from the deck."""


def extract_goal_progress_text(payload: MetricPayload) -> str:
    """Extract progress text for a metric in the deck.

    Returns "{display_value}" or "{display_value} / {target}".
    Appends [stale] badge if availability_state == "stale".

    Exists as a standalone function for cross-output consistency test import.
    """
    value = payload.display_value

    if payload.availability_state == "stale":
        value = value + " [stale]"

    if payload.target is not None and payload.availability_state not in ("needs_build", "null"):
        target_str = _format_target(payload.target, payload.format_spec)
        return value + " / " + target_str

    return value


def render_deck_updates(
    all_payloads: dict[str, list[MetricPayload]],
    snapshot_timestamp: str,
) -> tuple[list[SlideReplacement], list[ConsumerResult]]:
    """Build text replacement operations for the all-hands deck.

    Filters to leadership sensitivity (excludes founders_only).
    Placeholder format: {{dept_id_metric_registry_key_snake_case}}
    Returns per-metric ConsumerResult with consumer="slides_deck".
    """
    replacements: list[SlideReplacement] = []
    results: list[ConsumerResult] = []

    for dept_id, payloads in all_payloads.items():
        for p in payloads:
            # Filter: leadership sensitivity max (excludes founders_only)
            sensitivity_level = SENSITIVITY_LEVELS.get(p.sensitivity, 0)
            if sensitivity_level > SENSITIVITY_LEVELS["leadership"]:
                results.append(ConsumerResult(
                    registry_key=p.registry_key,
                    dept_id=dept_id,
                    consumer="slides_deck",
                    action="skipped",
                    error_message="sensitivity filtered (founders_only)",
                ))
                continue

            # Build placeholder from dept_id + registry_key
            placeholder = "{{" + _to_placeholder_key(dept_id, p.registry_key) + "}}"
            replacement_text = extract_goal_progress_text(p)

            replacements.append(SlideReplacement(
                placeholder=placeholder,
                replacement=replacement_text,
                dept_id=dept_id,
                metric_name=p.metric_name,
                registry_key=p.registry_key,
            ))

            results.append(ConsumerResult(
                registry_key=p.registry_key,
                dept_id=dept_id,
                consumer="slides_deck",
                action="delivered",
            ))

    return replacements, results


def apply_deck_updates(
    replacements: list[SlideReplacement],
    deck_id: str = DECK_ID,
    dry_run: bool = False,
) -> list[ConsumerResult]:
    """Apply replacements to the Google Slides deck via MCP.

    Verifies deck structure first (C4): missing placeholder → DeckStructureDriftError.
    No partial updates — all placeholders must exist before any are replaced.
    """
    results: list[ConsumerResult] = []

    if dry_run:
        for r in replacements:
            results.append(ConsumerResult(
                registry_key=r.registry_key,
                dept_id=r.dept_id,
                consumer="slides_deck",
                action="dry_run",
            ))
        return results

    # Verify all placeholders exist in the deck before applying
    slide_content = _get_slide_content(deck_id)

    missing = []
    for r in replacements:
        if r.placeholder not in slide_content:
            missing.append(r.placeholder)

    if missing:
        raise DeckStructureDriftError(
            "Expected placeholders missing from deck " + deck_id + ": " + ", ".join(missing)
            + ". Update the deck template or the placeholder mapping."
        )

    # MCP integration not yet wired — refuse to pretend we delivered
    raise NotImplementedError(
        "apply_deck_updates non-dry-run mode requires MCP integration "
        "(replaceAllTextInSlides). Use --dry-run until MCP is wired in the CLI layer."
    )


def _get_slide_content(deck_id: str) -> str:
    """Fetch full text content of the slides deck.

    In production, this calls the Google Slides MCP tool.
    Extracted as a function for easy mocking in tests.
    """
    # This will be wired to MCP getGoogleSlidesContent in the CLI layer
    raise NotImplementedError(
        "_get_slide_content requires MCP integration. "
        "Use apply_deck_updates with dry_run=True for testing."
    )


def _to_placeholder_key(dept_id: str, registry_key: str) -> str:
    """Convert dept_id + registry_key to a snake_case placeholder key.

    Example: ("sales", "Pipeline Coverage") → "sales_pipeline_coverage"
    """
    # Lowercase, replace spaces and special chars with underscores
    key = registry_key.lower()
    key = re.sub(r"[^a-z0-9]+", "_", key)
    key = key.strip("_")
    return dept_id + "_" + key


def _format_target(target: float, format_spec: str) -> str:
    """Format a target value for inline display in the deck."""
    if format_spec == "percent":
        if abs(target) <= 1:
            return str(round(target * 100, 1)) + "%"
        return str(round(target, 1)) + "%"
    elif format_spec in ("multiplier", "pipeline_gap"):
        return str(round(target, 1)) + "x"
    elif format_spec == "currency":
        if abs(target) >= 1_000_000:
            return "$" + str(round(target / 1_000_000, 1)) + "M"
        elif abs(target) >= 1_000:
            return "$" + str(round(target / 1_000)) + "K"
        return "$" + str(round(target))
    elif format_spec == "days":
        return str(round(target)) + " days"
    elif format_spec in ("count", "number"):
        return "{:,.0f}".format(target)
    return str(target)
