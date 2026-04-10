-- TRUTH MODEL: event (immutable). One row per action item, captured at meeting-wrap time.
-- Written via merge_events (INSERT-only on action_item_id).
-- Status reflects the state AT THE TIME OF CAPTURE ONLY — this table does NOT
-- track status changes over time. If an action item was "not_started" when
-- /meeting-wrap ran, that's what's recorded. Period.
--
-- If status-over-time tracking is needed later (Phase 2+), create a separate
-- eos_action_item_status_changes event table with natural key
-- (action_item_id, changed_at). Do NOT version status within this table —
-- the natural key is action_item_id alone, and MERGE is insert-only, so
-- a second row for the same action_item_id would be silently skipped.

CREATE TABLE IF NOT EXISTS `stitchdata-384118.App_Recess_OS.eos_l10_action_items` (
  action_item_id STRING NOT NULL,   -- natural key for MERGE (single-row-per-item)
  meeting_id STRING NOT NULL,
  dept STRING NOT NULL,
  meeting_date DATE NOT NULL,
  text STRING,
  owner_email STRING,
  due_on DATE,
  status STRING,                  -- 'done' | 'in_progress' | 'overdue' | 'not_started' | 'uncaptured' — at time of capture ONLY
  asana_task_gid STRING,          -- NULL if uncaptured
  matched_via STRING,             -- 'exact' | 'fuzzy' | 'none'
  created_at TIMESTAMP NOT NULL,
  synced_at TIMESTAMP NOT NULL,
  PRIMARY KEY (action_item_id) NOT ENFORCED
)
PARTITION BY meeting_date
CLUSTER BY dept, owner_email
OPTIONS (
  description = 'TRUTH MODEL: event (immutable). One row per action item at capture time. Status is point-in-time, NOT versioned. INSERT-only via merge_events on action_item_id.'
);
