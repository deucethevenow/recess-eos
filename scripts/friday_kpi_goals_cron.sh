#!/bin/bash
# Friday Asana Goals push wrapper.
#
# Honors DRY_RUN env var: set DRY_RUN=1 for cutover testing (Task 9 mid-week test).
# When DRY_RUN=1, --dry-run flag is added; output is diffable against last
# local-cron Friday log before allowing real writes to Asana Goals.

set -e

: "${ASANA_ACCESS_TOKEN:?required env var}"

echo "[Friday kpi-goals] Starting at $(date --iso-8601=seconds) (DRY_RUN=${DRY_RUN:-0})"

DRY_RUN_FLAG=""
[ "${DRY_RUN:-0}" = "1" ] && DRY_RUN_FLAG="--dry-run"

exec timeout --kill-after=15s 240s python /app/scripts/recess_os.py push-kpi-goals $DRY_RUN_FLAG
