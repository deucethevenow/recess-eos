-- Create the App_Recess_OS dataset for Recess OS operational data
-- Run once via: bq query --use_legacy_sql=false < 2026-04-10-create-dataset.sql

CREATE SCHEMA IF NOT EXISTS `stitchdata-384118.App_Recess_OS`
OPTIONS (
  description = 'Recess OS operational data — synced from Asana, BQ KPI snapshots, Airtable transcripts. Time-series store for status updates, L10 meetings, action items, project tracking.',
  location = 'US'
);
