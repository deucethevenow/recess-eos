-- TRUTH MODEL: snapshot — current state of all Recess projects.
-- Overwritten per sync via RecessOSBQClient.load_snapshot() (WRITE_TRUNCATE).
-- Deletions in Asana propagate by absence on next sync.
-- Not partitioned — there is only ever one current snapshot per gid.
-- custom_fields_json stores both fields_by_name and fields_by_gid (see Task 11).

CREATE TABLE IF NOT EXISTS `stitchdata-384118.App_Recess_OS.eos_projects` (
  asana_project_id STRING NOT NULL,
  name STRING,
  owner_email STRING,
  owner_name STRING,
  project_type STRING,           -- 'rock' | 'operational' | 'experiment' | 'customer' | 'infrastructure' | 'other'
  linked_rock_goal_id STRING,    -- NULL for non-Rock projects
  linked_rock_id STRING,         -- NULL for non-Rock projects
  status STRING,                 -- 'active' | 'paused' | 'done' | 'archived'
  quarter STRING,                -- 'Q2-2026'
  task_count INT64,
  completion_percent FLOAT64,
  last_activity_at TIMESTAMP,
  custom_fields_json STRING,     -- JSON {fields_by_name: {...}, fields_by_gid: {...}} — see Task 11
  synced_at TIMESTAMP NOT NULL,  -- audit only; not used for partitioning
  PRIMARY KEY (asana_project_id) NOT ENFORCED
)
OPTIONS (
  description = 'TRUTH MODEL: snapshot. All Recess Asana projects (Rock-linked + non-Rock). Overwritten via WRITE_TRUNCATE per sync. Distinguished by project_type + linked_rock_goal_id.'
);
