# Recess OS Learning Loop

## What This Is

A structured knowledge store for corrections to agent-generated code in the EOS project. When Claude makes a mistake that a human catches and fixes, the correction is documented here so the same mistake doesn't happen again.

## How to Use

**Capture a correction:** `/learn` (after fixing agent code)
**Surface learnings:** `learnings-researcher` agent (dispatched before feature work)
**Review before commit:** `/critic-review` (3-layer adversarial review)

## Categories

| Directory | What Goes Here |
|-----------|---------------|
| `patterns/` | Critical patterns (always loaded, max 10) |
| `config-contract-issues/` | Registry overrides, forbidden fields, silent defaults |
| `api-integration-issues/` | Airtable/Asana/Slack escaping, API quirks |
| `data-layer-issues/` | BQ, immutable events, payload errors, NaN |
| `type-safety-issues/` | Return type violations, safe_float contracts |
| `deployment-issues/` | Cron, Cloud Run, credentials, env vars |

## Schema

See `schema.yaml` for all valid enum values. All YAML list fields MUST use inline array format for grep-based retrieval.

## Relationship to context/LEARNINGS.md

`context/LEARNINGS.md` is the legacy gotcha log (monolithic, 11KB, 13 entries). Still valuable as historical record, but new corrections go to `.claude/learnings/` for structured, grep-searchable retrieval.
