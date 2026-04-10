-- TRUTH MODEL: snapshot — current state of all quarterly Rocks.
-- Overwritten per sync via load_snapshot (WRITE_TRUNCATE).
-- Historical rock progress lives in git (rock-NNN.md files) + eos_goal_metric_history.

CREATE TABLE IF NOT EXISTS `stitchdata-384118.App_Recess_OS.eos_rocks` (
  rock_id STRING NOT NULL,
  title STRING,
  owner STRING,
  quarter STRING,
  status STRING,
  due_date DATE,
  asana_goal_id STRING,
  asana_project_id STRING,
  milestones_total INT64,
  milestones_complete INT64,
  completion_percent FLOAT64,
  current_baseline_state STRING,
  synced_at TIMESTAMP NOT NULL,   -- audit only; not used for partitioning
  PRIMARY KEY (rock_id) NOT ENFORCED
)
OPTIONS (
  description = 'TRUTH MODEL: snapshot. Rock metadata synced from CEOS Git rock files + Asana milestone progress. Overwritten per sync.'
);
