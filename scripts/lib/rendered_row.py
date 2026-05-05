"""Single-source rendering contract for /monday-kpi-update.

Per v3.8 Patch 1 (closes B1 cross-output parity, B2 cache pinning, B17 placeholder
parity): every metric flows through one render function and emits one RenderedRow.
All three surface writers (deck, Slack, leadership doc) consume the SAME
row.display_label + row.display strings. They never re-format from raw values,
never recompute target strings, never resolve their own per-dept label.

Field semantics:
  metric_name    - canonical registry key (e.g., "Demand NRR"); used as a stable
                   identifier for tests/logs. NEVER use this as the user-facing
                   label — that's display_label.
  display_label  - per-dept user-facing label resolved via get_scorecard_label
                   (handles per-dept overrides like "Revenue YTD" → "Net Revenue YTD").
  display        - the canonical value-and-target string (e.g., "Q: $49K / $1.38M
                   (4%)  ·  target $1.5M"). Surface writers concatenate this with
                   their own bullet/separator formatting.
  is_phase2_placeholder - True iff display == "🔨 (Phase 2 migration)". Lets the
                   deck writer style the cell differently (gray, italics, etc.).
"""
from typing import NamedTuple, Optional


class RenderedRow(NamedTuple):
    metric_name: str
    display_label: str
    dept_id: str
    sensitivity: str
    actual_raw: Optional[float]
    target_raw: Optional[float]
    status_icon: str
    display: str
    is_phase2_placeholder: bool
    is_special_override: bool
