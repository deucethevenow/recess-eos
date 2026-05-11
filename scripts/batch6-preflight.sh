#!/bin/bash
# Batch 6 preflight — verify all 5 prerequisites before starting Cloud Run Jobs migration.
# Plan: ~/Projects/eos/context/plans/2026-04-23-cloud-run-jobs-monday-pulse-migration.md
# Run from worktree: ~/Projects/eos-batch-6-cloud-run/scripts/batch6-preflight.sh
set -e
echo "=== Batch 6 preflight ==="

# 1. PR #1 (recess-eos) merged — origin/main HEAD must include the Batch 4 cron commit.
#    (Soft check: subject grep instead of literal SHA — squash/rebase merges rewrite SHAs.)
cd ~/Projects/eos
git fetch origin main >/dev/null 2>&1
if git log origin/main --oneline | grep -q "Batch 4: Monday cron calls KPI Dashboard pulse"; then
  echo "✅ eos origin/main contains Batch 4 cron commit (PR #1 merged)"
else
  echo "❌ PR #1 not merged into origin/main"
  echo "   origin/main: $(git rev-parse --short origin/main)"
  exit 1
fi

# 2. Dashboard Batch 3 merged to origin/main — check by commit subject.
cd ~/Projects/company-kpi-dashboard
git fetch origin main >/dev/null 2>&1
if git log --oneline origin/main | grep -q "Batch 3 — Monday Pulse Slack poster"; then
  echo "✅ Batch 3 merged (commit subject in origin/main)"
else
  echo "❌ BLOCKER: Dashboard Batch 3 ('Monday Pulse Slack poster') not in origin/main — push dashboard first"
  exit 1
fi

# 3. gcloud authenticated to stitchdata-384118
if gcloud config get-value project 2>/dev/null | grep -q stitchdata-384118; then
  echo "✅ gcloud on stitchdata-384118"
else
  echo "❌ gcloud config set project stitchdata-384118"
  exit 1
fi

# 4. Docker running
if docker ps >/dev/null 2>&1; then
  echo "✅ Docker running"
else
  echo "❌ Start Docker Desktop"
  exit 1
fi

# 5. Local .env tokens present
for V in SLACK_BOT_TOKEN ASANA_ACCESS_TOKEN RECESS_PROJECTS_PORTFOLIO_GID; do
  if grep -q "^${V}=" ~/Projects/daily-brief-agent/.env; then
    echo "✅ $V in .env"
  else
    echo "❌ $V missing from .env"
    exit 1
  fi
done

echo "=== Preflight PASSED ==="
