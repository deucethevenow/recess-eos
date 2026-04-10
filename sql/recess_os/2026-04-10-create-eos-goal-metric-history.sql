-- TRUTH MODEL: event (immutable). Time series of every Asana Goal metric push.
-- Written via merge_events with composite natural key (asana_goal_id, pushed_at).
-- Each push creates one row; retries at different timestamps create multiple rows
-- (accurate audit trail of all push attempts). Filter by pushed_by='cron' for
-- "intentional pushes only" in consumer queries.

CREATE TABLE IF NOT EXISTS `stitchdata-384118.App_Recess_OS.eos_goal_metric_history` (
  asana_goal_id STRING NOT NULL,   -- part of composite natural key
  goal_name STRING,
  pushed_value FLOAT64,
  raw_bq_value FLOAT64,
  transform_used STRING,          -- 'raw' | 'percent_higher_is_better' | 'percent_lower_is_better'
  source_table STRING,
  source_column STRING,
  pushed_at TIMESTAMP NOT NULL,   -- part of composite natural key
  pushed_by STRING                -- 'cron' | 'manual_command' | 'retry'
)
PARTITION BY DATE(pushed_at)
CLUSTER BY asana_goal_id
OPTIONS (
  description = 'TRUTH MODEL: event (immutable). Time series of every value pushed to an Asana Goal metric. Used for trend analysis + audit.',
  partition_expiration_days = 730
);
