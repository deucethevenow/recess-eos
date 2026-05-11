"""Phase B+ surface adapter — Asana founders pre-read.

NEW MODULE (Phase B+, 2026-05-10). Closes the dual-pipeline loophole flagged
by Phase 0 reviewers: today, scripts/monday_kpi_update.py:316 calls
render_one_row(...) for ALL departments including founders, and that path
consumes the registry's `scorecard_status` field. The other three surfaces
(Slack/Deck/Leadership-doc) consume yaml status via the canonical MetricPayload
pipeline. Without this adapter, "Phase B+ done" could mean Slack/Deck/Doc
unified while founders pre-read still drifts on the legacy path.

This module is a thin pass-through to metric_payloads.build_metric_payloads —
the same producer that Slack/Deck/Doc adapters call. Founders-specific render
fan-out (Asana subtask body composition, sensitivity filter to founders_only)
lives in the call site at monday_kpi_update.py, NOT here. Adapters are
producers; rendering is downstream.
"""
from typing import List

from .metric_payloads import MetricPayload, build_metric_payloads


def build_payloads_for_founders_preread(
    meeting: dict,
    snapshot_row: dict,
    snapshot_timestamp: str,
) -> List[MetricPayload]:
    """Build canonical MetricPayload list for the founders pre-read surface.

    Identical contract to build_payloads_for_slack/deck/doc — same producer,
    same args, same fields. Cross-surface parity is enforced by construction.
    """
    return build_metric_payloads(meeting, snapshot_row, snapshot_timestamp)
