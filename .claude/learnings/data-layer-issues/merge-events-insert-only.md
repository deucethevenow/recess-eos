---
module: BigQuery Client
date: 2026-04-11
problem_type: immutable_event_violation
component: bq_client
symptoms: ["Agent added WHEN MATCHED THEN UPDATE to MERGE statement", "Attempted to update existing event row", "Event table showed stale data after re-run"]
root_cause: immutable_design_conflict
severity: critical
tags: [merge, events, insert-only, immutable, bigquery, write-once]
affected_files: [scripts/lib/bq_client.py, scripts/asana_eos_sync.py]
resolution_type: documentation_update
elevated_to_critical: true
---
# merge_events() is INSERT-only — no UPDATE clause

## What the agent does wrong

Adds `WHEN MATCHED THEN UPDATE` to the MERGE statement for event tables:

```sql
-- WRONG — event tables are write-once
MERGE target USING staging ON natural_key
WHEN MATCHED THEN UPDATE SET ...    ← FORBIDDEN
WHEN NOT MATCHED THEN INSERT (...)
```

## Why it's wrong

Event tables in Recess OS are **immutable by design**. Each row is written once per natural key and never updated. This is a deliberate architectural decision for:
- Audit integrity (no retroactive changes)
- Idempotent re-runs (MERGE with INSERT-only is naturally idempotent)
- Simplified debugging (row = truth at write time)

If you need to "update" an event, the correct approach is to write a NEW event with a new natural key (e.g., append a version or timestamp).

## Correct pattern

```sql
-- RIGHT — INSERT-only MERGE (write-once per natural key)
MERGE target USING staging ON natural_key
WHEN NOT MATCHED THEN INSERT (col1, col2, ...)
VALUES (staging.col1, staging.col2, ...)
```

## Prevention

- If you need to track state changes over time, use a separate state table (not events)
- The "skipped" status addition was done correctly — it's a new status value, not an update to existing rows
- If the architecture truly needs UPDATE capability, that's a design discussion — not a quick code change
