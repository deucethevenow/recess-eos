-- TRUTH MODEL: event (immutable). One row per L10 meeting.
-- Written via merge_events (INSERT-only on meeting_id). Never updated in place.
-- Written by /meeting-wrap closed loop (Phase 2), not by sync_to_bq.

CREATE TABLE IF NOT EXISTS `stitchdata-384118.App_Recess_OS.eos_l10_meetings` (
  meeting_id STRING NOT NULL,      -- natural key for MERGE
  dept STRING NOT NULL,           -- 'leadership' | 'sales' | 'am' | etc.
  meeting_date DATE NOT NULL,
  facilitator_email STRING,
  asana_card_gid STRING,
  airtable_record_id STRING,
  fireflies_transcript_url STRING,
  summary STRING,
  scorecard_snapshot_json STRING, -- JSON: {metric: value, ...}
  rocks_reviewed_json STRING,     -- JSON array of rock_ids
  issues_count INT64,
  todos_created_count INT64,
  source STRING,                  -- 'auto' (cron) | 'manual'
  synced_at TIMESTAMP NOT NULL,
  PRIMARY KEY (meeting_id) NOT ENFORCED
)
PARTITION BY meeting_date
CLUSTER BY dept
OPTIONS (
  description = 'TRUTH MODEL: event (immutable). One row per L10 meeting. Created by /meeting-wrap closed loop. INSERT-only — never updated.'
);
