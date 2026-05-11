#!/bin/bash
# Daily sync wrapper — Asana portfolio → BigQuery App_Recess_OS.
#
# Reads RECESS_PROJECTS_PORTFOLIO_GID from env (mounted Secret Manager value).
# Avoids leaking the GID into `gcloud run jobs describe` output via --args.

set -e

: "${RECESS_PROJECTS_PORTFOLIO_GID:?required env var}"
: "${ASANA_ACCESS_TOKEN:?required env var}"

echo "[Daily sync] Starting at $(date --iso-8601=seconds)"

# 900s allows for Asana 429 retries on slow days. Cloud Run Job task-timeout is 600s
# in Task 7 — that's the binding ceiling; this wrapper-level 900s is a no-op upper
# bound, kept for defense-in-depth and to make intent explicit.
exec timeout --kill-after=15s 900s python /app/scripts/recess_os.py sync-to-bq \
  --portfolio "$RECESS_PROJECTS_PORTFOLIO_GID" \
  --cron-trigger cloud-scheduler
