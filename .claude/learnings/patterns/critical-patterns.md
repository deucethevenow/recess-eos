# Recess OS Critical Patterns

> **This file is always loaded by the learnings-researcher regardless of search results.**
> Patterns here are elevated from .claude/learnings/ when captured 3+ times OR severity: critical.
> **Hard cap: 10 entries.** When full, remove or merge an entry before adding.

## 1. Registry is GOD — Config Cannot Override

NEVER put `transform`, `format`, `higher_is_better`, or any logic field in `recess_os.yml`. These live ONLY in `metric_registry.py` in the KPI Dashboard project.
**Why:** `kpi_goals.yml` was a parallel logic engine that drifted from registry — deprecated entirely. `FORBIDDEN_CONFIG_LOGIC_FIELDS` in `metric_contract.py` enforces this. `test_kpi_config_consistency.py` is the drift guard.
**Source:** .claude/learnings/config-contract-issues/config-cannot-override-registry.md

## 2. Fail Loud — No Silent Defaults on Contract Fields

NEVER use `.get(field, default)` for contract-critical fields (format, higher_is_better, bq_key). Missing fields MUST raise `ContractResolutionError`.
**Why:** Silent defaults hide schema corruption. A missing `format` field degrades to `None` and renders as raw float in Slack — no one notices until a stakeholder asks "why does this say 0.6512?"
**Correct:** Access directly: `entry["format"]` — let KeyError propagate. Or use explicit validation in `metric_contract.py`.

## 3. Airtable Escaping: Backslash for Apostrophes

Use `\'` (backslash) for apostrophes in Airtable `filterByFormula`, NOT SQL-style `''`.
**Also:** Escape backslash FIRST, then apostrophe: `value.replace("\\", "\\\\").replace("'", "\\'")`
**Why:** Airtable API returns 422 on SQL-style escaping. Caused Fireflies transcript pull failures for meetings with apostrophes in attendee names.
**Guard:** Integration test with real Airtable hitting apostrophe-bearing input.

## 4. merge_events() is INSERT-Only (Immutable Events)

Event tables use MERGE with ONLY `WHEN NOT MATCHED THEN INSERT`. No `WHEN MATCHED THEN UPDATE` clause.
**Why:** Event tables are write-once by natural key. This is a design decision, not a bug. If you need to update in-progress runs, the architecture needs to change — don't just add an UPDATE clause.
**Applies to:** `bq_client.py` staging functions, `asana_eos_sync.py` event tables.

## 5. safe_float(default=None) Violates Type Contract

NEVER pass `default=None` to `safe_float()`. Its return type is `float` with default `0.0`. Passing `None` makes it return `Optional[float]`, breaking downstream arithmetic.
**Correct:** Use `_safe_optional_float()` sibling for nullable values.
**Source:** .claude/learnings/type-safety-issues/safe-float-none-default.md

## 6. Fireflies Titles Don't Match Config Names

Fireflies meeting titles are calendar-event names ("Recess Chat", "Sales Weekly"), NOT the verbose names in `recess_os.yml` ("Sales L10", "Demand AM L10").
**Correct:** Two-pass fallback: try exact title match first, then surface top 3 candidates for manual confirmation.
**Applies to:** `airtable_client.py` transcript lookup, any Fireflies integration.

## 7. Asana = Execution, Git = Strategy

Rock definitions (title, outcome, milestones) live in Git (`data/rocks/`). Execution tracking (tasks, progress, status updates) lives in Asana. BQ syncs from Asana hourly for reporting.
**NEVER duplicate:** Don't track task completion in Git. Don't put strategy prose in Asana descriptions.

## 8. Config Goals are Pointer-Only

Goals in `recess_os.yml` MUST contain ONLY: `asana_goal_id`, `registry_key`, `target`, `sensitivity`, `status`, `null_behavior`. No logic fields (transform, format, higher_is_better — those come from registry via contract resolution).
**Guard:** `metric_contract.py` raises `ContractResolutionError` if forbidden fields detected.

## 9. Snapshot-Driven Metrics — Same Rule as KPI Dashboard

All metrics with `status: automated` pull from `kpi_daily_snapshot` table. Never add live BQ queries for metrics the snapshot already has.
**Why:** Same as KPI Dashboard — consistency, performance, single source of truth.
**Applies to:** `metric_payloads.py` payload building, `monday_pulse.py`, `kpi_goals_pusher.py`.

## 10. Sensitivity Routing — Never Leak Leadership/Founders Data

Meetings have sensitivity levels: `public`, `leadership`, `founders_only`. Consumers MUST check sensitivity before including metrics in output.
**Why:** Leadership scorecard metrics and founders-only data must not appear in public Slack channels or all-hands decks.
**Applies to:** `monday_pulse.py`, `all_hands_deck.py`, any new consumer.
