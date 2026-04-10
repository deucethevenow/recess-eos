#!/usr/bin/env bash
# Recess OS daily cron — runs every day at 8am Eastern.
# Internal day-of-week + bi-weekly parity dispatch.
#
# Triggered by Cloud Scheduler job: recess-os-daily
# Schedule: 0 13 * * *  (UTC = 8am Eastern)

set -euo pipefail

# ── Resolve script directory (works from worktree or main repo) ──────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# ── Source third-party credentials ───────────────────────────────────────
set -a; source "$HOME/Projects/daily-brief-agent/.env" 2>/dev/null || true; set +a

# ── Set BQ credentials (local dev only; Cloud Run uses ADC) ──────────────
export GOOGLE_APPLICATION_CREDENTIALS="${GOOGLE_APPLICATION_CREDENTIALS:-$HOME/.config/bigquery-mcp-key.json}"

# ── Determine day of week (1=Mon ... 7=Sun) ──────────────────────────────
DOW=$(date +%u)

# ── Always run sync (every day) ──────────────────────────────────────────
.venv/bin/python recess_os.py sync-to-bq \
  --portfolio "$RECESS_PROJECTS_PORTFOLIO_GID" \
  --cron-trigger cloud-scheduler

# ── Day-specific dispatches (Phase 4 will add these) ─────────────────────
case "$DOW" in
  1) echo "Monday — would run monday-pulse (Phase 4)" ;;
  3) echo "Wednesday — would run send-preread (Phase 4)" ;;
  5) echo "Friday — would run push-kpi-goals (Phase 4)" ;;
esac

# ══════════════════════════════════════════════════════════════════════════
# PRODUCTION CREDENTIALS SETUP (one-time, run manually when ready)
# ══════════════════════════════════════════════════════════════════════════
#
# 1. Create the Asana PAT secret in Secret Manager:
#
#   gcloud secrets create recess-os-asana-pat \
#     --project=stitchdata-384118 \
#     --replication-policy=automatic
#   echo -n "${ASANA_ACCESS_TOKEN}" | gcloud secrets versions add recess-os-asana-pat --data-file=-
#
# 2. Grant the Cloud Run service account access to the secret:
#
#   gcloud secrets add-iam-policy-binding recess-os-asana-pat \
#     --project=stitchdata-384118 \
#     --member="serviceAccount:bigquery-mcp@stitchdata-384118.iam.gserviceaccount.com" \
#     --role="roles/secretmanager.secretAccessor"
#
# 3. Grant the service account write access to App_Recess_OS dataset:
#
#   bq add-iam-policy-binding \
#     --member="serviceAccount:bigquery-mcp@stitchdata-384118.iam.gserviceaccount.com" \
#     --role="roles/bigquery.dataEditor" \
#     stitchdata-384118:App_Recess_OS
#
# ══════════════════════════════════════════════════════════════════════════
# CLOUD SCHEDULER DEPLOYMENT (one-time, when migrating from local cron)
# ══════════════════════════════════════════════════════════════════════════
#
# gcloud scheduler jobs create http recess-os-daily \
#   --project=stitchdata-384118 \
#   --location=us-central1 \
#   --schedule="0 13 * * *" \
#   --time-zone="UTC" \
#   --uri="https://<cloud-run-service-url>/run" \
#   --http-method=POST \
#   --headers="Authorization=Bearer <oidc-token>"
#
# Cloud Run service deployment is a separate task —
# this script can also run on a local cron initially.
#
# ══════════════════════════════════════════════════════════════════════════
# LOCAL CRON (interim — until Cloud Run is set up)
# ══════════════════════════════════════════════════════════════════════════
#
# Add to crontab (crontab -e):
#   0 8 * * * /Users/deucethevenowworkm1/Projects/eos/scripts/recess_os_daily.sh >> ~/Projects/eos/scripts/cron.log 2>&1
