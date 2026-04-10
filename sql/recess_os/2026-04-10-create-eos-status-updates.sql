-- TRUTH MODEL: event (immutable). All status updates ever posted to Asana Goals or Projects.
-- Append-only via RecessOSBQClient.merge_events() with natural key status_update_gid.
-- MERGE uses WHEN NOT MATCHED THEN INSERT only — rows are NEVER updated once written.
-- To correct a mistake, write a new row with later created_at and filter in consumer views.
-- Single table with parent_type discriminator (vs separate tables per parent).
-- 2-year retention — status updates are historical and cheap to store.

CREATE TABLE IF NOT EXISTS `stitchdata-384118.App_Recess_OS.eos_status_updates` (
  status_update_gid STRING NOT NULL,  -- natural key for MERGE
  parent_type STRING NOT NULL,    -- 'goal' | 'project'
  parent_gid STRING NOT NULL,
  parent_name STRING,
  status_type STRING,             -- 'on_track' | 'at_risk' | 'off_track' | 'achieved' | 'dropped'
  text STRING,
  source STRING,                  -- 'auto' (Sunday cron) | 'manual' (human in Asana UI)
  author_email STRING,
  author_name STRING,
  created_at TIMESTAMP NOT NULL,
  synced_at TIMESTAMP NOT NULL,
  PRIMARY KEY (status_update_gid) NOT ENFORCED
)
PARTITION BY DATE(created_at)
CLUSTER BY parent_gid, parent_type
OPTIONS (
  description = 'TRUTH MODEL: event (immutable). All Goal and Project status updates from Asana. Written via merge_events (INSERT-only on natural key). source=auto vs manual distinguishes cron-generated from human-written.',
  partition_expiration_days = 730
);
