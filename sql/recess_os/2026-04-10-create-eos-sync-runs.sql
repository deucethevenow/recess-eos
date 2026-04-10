-- TRUTH MODEL: event (immutable). One row per (sync run, table touched).
-- Written by the @sync_instrumented decorator in Task 10.5.
-- Plus a top-level (run_id, 'ALL') row for each sync summarizing the whole run.
-- Powers the 3 SLO queries defined in the Observability section above.

CREATE TABLE IF NOT EXISTS `stitchdata-384118.App_Recess_OS.eos_sync_runs` (
  run_id STRING NOT NULL,           -- UUID4 generated at sync start
  table_name STRING NOT NULL,       -- e.g. 'eos_projects' or 'ALL' for run summary
  started_at TIMESTAMP NOT NULL,
  ended_at TIMESTAMP,               -- NULL = still running or crashed mid-write
  status STRING,                    -- 'running' | 'success' | 'failed'
  row_count INT64,                  -- rows written to this table this run
  duration_seconds FLOAT64,
  error_message STRING,             -- NULL on success
  git_sha STRING,                   -- git rev-parse HEAD at sync start (from env var)
  cron_trigger STRING,              -- 'cloud-scheduler' | 'manual' | 'backfill' | 'test'
  PRIMARY KEY (run_id, table_name) NOT ENFORCED
)
PARTITION BY DATE(started_at)
CLUSTER BY table_name, status
OPTIONS (
  description = 'TRUTH MODEL: event (immutable). One row per (sync run, table). Written by @sync_instrumented decorator. Powers the 3 SLO health checks for Recess OS.',
  partition_expiration_days = 180
);
