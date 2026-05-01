#!/bin/bash
# Monday cron wrapper — pulse + deck refresh, run sequentially with per-step timeouts.
#
# Both steps run regardless of the other's exit status; overall exit reflects whether
# ALL steps succeeded so Cloud Monitoring alerts fire on partial failures.
#
# DECK_ENABLED feature flag (default 0):
#   The deck step is gated behind DECK_ENABLED because all_hands_deck.py's MCP
#   integration is unwired (apply_deck_updates raises NotImplementedError on the
#   real write path). Until the Google Slides MCP integration lands (Batch 7),
#   running the deck step crashes on goals weeks → alert fatigue every 2 weeks.
#
#   Re-enable when MCP is wired:
#     gcloud run jobs update monday-jobs --update-env-vars=DECK_ENABLED=1 \
#       --region=us-central1 --project=stitchdata-384118
#
#   No image rebuild required — pure config change.
#
# `update-all-hands-deck --check-cadence` exits 0 silently on projects-weeks
# (see update_all_hands_deck_cmd in scripts/recess_os.py). On goals-weeks it
# would attempt the real write path, which is the path that currently raises
# NotImplementedError.

set +e

echo "[Monday cron] Starting at $(date --iso-8601=seconds)"

echo "[Monday cron] Step 1/2: Monday Pulse"
# 360s = generous buffer over local cron times (~30-60s) for cold start + BQ snapshot read.
timeout --kill-after=15s 360s python /app/scripts/post_monday_pulse.py --post
PULSE_EXIT=$?
[ $PULSE_EXIT -eq 124 ] \
  && echo "[Monday cron] Pulse TIMED OUT (360s)" \
  || echo "[Monday cron] Pulse exit: $PULSE_EXIT"

echo "[Monday cron] Step 2/2: Update All-Hands deck (DECK_ENABLED=${DECK_ENABLED:-0})"
if [ "${DECK_ENABLED:-0}" = "1" ]; then
  timeout --kill-after=15s 240s python /app/scripts/recess_os.py update-all-hands-deck --check-cadence
  DECK_EXIT=$?
  [ $DECK_EXIT -eq 124 ] \
    && echo "[Monday cron] Deck TIMED OUT (240s)" \
    || echo "[Monday cron] Deck exit: $DECK_EXIT"
else
  echo "[Monday cron] Deck step DISABLED — pending MCP integration (Batch 7)"
  echo "[Monday cron] To re-enable: gcloud run jobs update monday-jobs --update-env-vars=DECK_ENABLED=1"
  DECK_EXIT=0
fi

if [ $PULSE_EXIT -ne 0 ] || [ $DECK_EXIT -ne 0 ]; then
  echo "[Monday cron] PARTIAL FAILURE: pulse=$PULSE_EXIT deck=$DECK_EXIT"
  exit 1
fi

echo "[Monday cron] All steps succeeded"
exit 0
