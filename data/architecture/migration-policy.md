# Recess OS — Schema Migration Policy

> **Status:** Active. Governs all schema changes to the `App_Recess_OS` BigQuery dataset.
>
> **Created:** 2026-04-09 as part of Rock 7 Phase 1 hardening (post-adversarial-review).
>
> **Owners:** Deuce (architecture), whoever is on-call for Recess OS.

---

## Purpose

BigQuery is not friendly to schema changes. Partitioning, clustering, and column types are effectively immutable once a table is created — the only "migration" path for structural changes is drop-and-recreate. Additive changes (new nullable columns) are easy. Destructive changes are not.

This document defines **which schema changes are safe**, **which require backfills**, and **how to roll back** if something goes wrong. Follow it before changing any SQL file in `sql/recess_os/`.

---

## Change Classification

| Change type | Primitive | Safe to run in prod? | Requires backfill? |
|---|---|---|---|
| Add a new nullable column | `ALTER TABLE ADD COLUMN` | ✅ Yes, immediately | ❌ Only new rows have the value |
| Rename a column | `ALTER TABLE RENAME COLUMN` (BQ 2023+) | ⚠️ Breaks consumer queries until updated | ❌ No data move |
| Change a column type | NOT SUPPORTED — drop + recreate | ❌ Destructive | ✅ Full backfill |
| Drop a column | `ALTER TABLE DROP COLUMN` | ⚠️ Breaks consumer queries | ❌ Data is gone |
| Change partitioning | NOT SUPPORTED — drop + recreate | ❌ Destructive | ✅ Full backfill (snapshot tables) or CSV dump (event tables) |
| Change clustering | NOT SUPPORTED — drop + recreate | ❌ Destructive | ✅ Full backfill |
| Change `partition_expiration_days` | `ALTER TABLE SET OPTIONS` | ✅ Safe | ❌ Affects future expiration only |
| Change table description | `ALTER TABLE SET OPTIONS` | ✅ Safe | ❌ N/A |

**Rule:** If you're unsure which category a change falls into, default to drop-and-recreate. It's the safer bet.

---

## Versioning Convention

All SQL migration files live in `sql/recess_os/` with the naming convention:

```
YYYY-MM-DD-NNN-short-description.sql
```

Where:
- `YYYY-MM-DD` is the date the migration was authored
- `NNN` is a 3-digit sequence number within that day (`001`, `002`, ...)
- `short-description` is a kebab-case description of the change

Examples:
- `2026-04-10-001-create-dataset.sql`
- `2026-04-10-002-create-eos-projects.sql`
- `2026-04-15-001-add-competitor-detected-to-eos-projects.sql`
- `2026-05-03-001-drop-and-recreate-eos-l10-meetings-with-new-partitioning.sql`

Each migration SQL file begins with a comment block:

```sql
-- Migration: 2026-04-15-001-add-competitor-detected-to-eos-projects
-- Author: Deuce
-- Change class: Additive (ALTER TABLE ADD COLUMN)
-- Safe to run in prod: YES
-- Backfill required: NO (new column is nullable)
-- Rollback: ALTER TABLE DROP COLUMN competitor_detected
-- Consumer impact: None — nullable column, existing queries unaffected
```

The header is parseable by future automation. Keep the fields exactly as shown.

---

## Standard Paths by Change Type

### Additive change (new nullable column)

1. Write the migration SQL with `ALTER TABLE ADD COLUMN`.
2. Apply locally: `bq query --use_legacy_sql=false --project_id=stitchdata-384118 < path/to/migration.sql`
3. Verify: `bq show --schema stitchdata-384118:App_Recess_OS.<table>`
4. Update consumer code (views, skills, CLI commands) to read the new column.
5. Commit migration SQL + consumer updates in ONE commit: `feat(recess-os): add <column> to <table>`

### Destructive change to a snapshot table (drop and recreate)

Snapshot tables are cheap to drop because the next sync will re-populate them in full.

1. Write the migration SQL as a two-stage file:
   ```sql
   DROP TABLE IF EXISTS `stitchdata-384118.App_Recess_OS.eos_projects`;
   -- (paste new CREATE TABLE here, with the change)
   ```
2. **Announce in Slack #eos-os-dev** (or the equivalent channel) 5 minutes before running. Anyone querying the table will see transient errors.
3. Apply the migration.
4. Run `recess_os sync-to-bq --portfolio <gid> --cron-trigger backfill` immediately to re-populate.
5. Verify row counts match the expected ballpark.
6. Commit: `schema-change(recess-os): recreate eos_projects with <change>`

### Destructive change to an event table (CSV dump + recreate + reload)

Event tables are IMMUTABLE history — dropping them loses data permanently. Back them up first.

1. **Export the current table to CSV (local) and to a GCS bucket (remote backup):**
   ```bash
   bq extract --destination_format=CSV \
     stitchdata-384118:App_Recess_OS.eos_status_updates \
     gs://recess-os-backups/eos_status_updates/$(date +%F).csv

   bq extract --destination_format=CSV \
     stitchdata-384118:App_Recess_OS.eos_status_updates \
     /tmp/eos_status_updates_backup_$(date +%F).csv
   ```
2. Write the migration SQL: DROP then CREATE.
3. Apply.
4. Write a one-off backfill script `scripts/backfills/YYYY-MM-DD-restore-eos-status-updates.py` that reads the CSV and writes rows via `RecessOSBQClient.merge_events`. Test locally first.
5. Run the backfill. Verify row count matches the pre-drop count (modulo any intentional transforms).
6. Commit the migration SQL + backfill script in ONE commit: `schema-change(recess-os): recreate eos_status_updates with <change>`.
7. **Retain the CSV backup for 30 days minimum** before deleting.

### Type change on an existing column

BigQuery does NOT support `ALTER TABLE ALTER COLUMN TYPE`. You have two options:

**Option A: New column, dual-write period, drop old**
1. `ALTER TABLE ADD COLUMN <new_col_name> <new_type>`
2. Update sync code to write both old and new columns.
3. Wait one sync cycle (or longer) for `<new_col_name>` to be populated.
4. Backfill `<new_col_name>` from `<old_col_name>` via a one-off script (type cast).
5. Update consumers to read `<new_col_name>`.
6. `ALTER TABLE DROP COLUMN <old_col_name>`.

**Option B: Drop and recreate** (for snapshot tables only)
Follow the "destructive change to a snapshot table" path above.

---

## Rollback Procedure

If a migration causes production issues, the rollback path depends on the change class:

| Change class | Rollback | Data loss? |
|---|---|---|
| Additive (ADD COLUMN) | `ALTER TABLE DROP COLUMN <col>` | No |
| RENAME | Rename back | No |
| DROP snapshot table (then recreate) | Re-run `sync-to-bq --cron-trigger backfill` | No (Asana is source of truth) |
| DROP event table + failed backfill | Restore from GCS CSV backup via backfill script | Depends on backup freshness |

For destructive changes to event tables, **the CSV backup from Step 1 is the rollback primitive**. If the backfill script fails or produces wrong data, you can re-run it from the CSV. If the new schema itself is wrong, drop again and recreate with the old schema, then re-run the backfill.

**Never attempt a rollback without:**
- A known-good CSV export of event tables
- Verification that the backfill script produces the expected row count
- Confirmation that consumer queries still work against the old schema

---

## Migrations That Should NEVER Happen

These changes should be refused outright:

1. **Changing the natural key of an event table.** If `eos_status_updates` natural key changes from `status_update_gid` to something else, all previous MERGE-based inserts are invalidated. Instead, create a new table with the new key and dual-write.
2. **Changing a column type on an event table without a backup.** Per the migration policy, event tables are immutable; lose data without a backup and it's gone.
3. **Adding a `WHEN MATCHED THEN UPDATE` clause to `merge_events`.** Event tables are immutable by architectural rule. If this feels necessary, you're solving the wrong problem — write a new event row with later timestamp and dedupe in a view.
4. **Dropping `eos_sync_runs`.** This is the observability table. Dropping it blinds us to sync health. If the schema needs to change, back it up like any other event table.

---

## Dataset-Level Settings

The `App_Recess_OS` dataset has these global settings that affect all tables:

```sql
-- Applied to the dataset once at creation time:
ALTER SCHEMA `stitchdata-384118.App_Recess_OS`
SET OPTIONS (
  description = 'Recess OS operational data — synced from Asana, BQ KPI snapshots, Airtable transcripts. Time-series store for status updates, L10 meetings, action items, project tracking.'
);
```

Staging tables created by `merge_events` set their own `expiration_time` at creation to 7 days. No dataset-wide default expiration is set — we want snapshot tables to live indefinitely.

---

## Review Checklist (before merging any schema change)

- [ ] SQL file follows naming convention `YYYY-MM-DD-NNN-description.sql`
- [ ] Header comment block includes: Migration, Author, Change class, Safe to run in prod, Backfill required, Rollback, Consumer impact
- [ ] Change class is correctly identified (additive vs destructive)
- [ ] Consumer code updated in the same PR/commit
- [ ] For event table changes: CSV backup command documented in PR description
- [ ] For destructive changes: Slack announcement drafted
- [ ] Rollback command(s) explicitly written out in the PR description
- [ ] Test run against a sandbox dataset or local BQ emulator before prod

---

## Example: Adding `custom_fields_json` to `eos_projects` (Phase 1.5)

This is the first expected migration after Phase 1. Full worked example:

```sql
-- sql/recess_os/2026-04-13-001-add-custom-fields-json-to-eos-projects.sql
-- Migration: 2026-04-13-001-add-custom-fields-json-to-eos-projects
-- Author: Deuce
-- Change class: Additive (ALTER TABLE ADD COLUMN)
-- Safe to run in prod: YES
-- Backfill required: NO (new rows populated by next sync; old rows will have NULL until overwritten)
-- Rollback: ALTER TABLE DROP COLUMN custom_fields_json
-- Consumer impact: None until Phase 1.5's v_abm_portfolio_status view is created

ALTER TABLE `stitchdata-384118.App_Recess_OS.eos_projects`
ADD COLUMN custom_fields_json STRING;
```

After applying this, the next `sync-to-bq` run will TRUNCATE + LOAD all projects, populating the new column with the dual-format JSON per the Phase 1.5 schema. Because `eos_projects` is a snapshot table, there's no backfill needed — the overwrite does it automatically.

Then Phase 1.5's `v_abm_portfolio_status` view can be created and will find the column populated.

Total downtime: zero. This is the "cheap path" and should be the default for any additive change.
