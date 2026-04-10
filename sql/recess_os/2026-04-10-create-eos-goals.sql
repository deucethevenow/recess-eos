-- TRUTH MODEL: snapshot — current state of all Asana Goals.
-- Overwritten per sync via load_snapshot (WRITE_TRUNCATE).
-- Enables Phase 4 deck updater to read from BQ instead of live Asana calls.
-- Sunday cron pushes goal values to Asana → next sync_to_bq run pulls them
-- back into this table → Monday deck cron reads from here.

CREATE TABLE IF NOT EXISTS `stitchdata-384118.App_Recess_OS.eos_goals` (
  asana_goal_id STRING NOT NULL,
  name STRING,
  owner_email STRING,
  owner_name STRING,
  time_period STRING,             -- 'Q2 FY26'
  metric_unit STRING,             -- 'percentage' | 'number' | 'currency'
  current_number_value FLOAT64,   -- raw value from Asana
  target_number_value FLOAT64,
  percent_complete FLOAT64,       -- derived: current / target * 100
  current_display_value STRING,   -- human-readable e.g. "47%" or "$1.2M"
  due_on DATE,
  start_on DATE,
  status_text STRING,             -- latest status update text
  status_type STRING,             -- 'on_track' | 'at_risk' | 'off_track' | 'achieved'
  notes STRING,
  synced_at TIMESTAMP NOT NULL,   -- audit only; not used for partitioning
  PRIMARY KEY (asana_goal_id) NOT ENFORCED
)
OPTIONS (
  description = 'TRUTH MODEL: snapshot. Asana Goal metadata + metric values. Overwritten via WRITE_TRUNCATE per sync. Read by Phase 4 deck updater + ceos-dashboard.'
);
