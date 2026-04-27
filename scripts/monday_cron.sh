#!/bin/bash
# Monday cron wrapper — pulse + deck refresh, run sequentially with per-step timeouts.
#
# Both steps run regardless of the other's exit status; overall exit reflects whether
# ALL steps succeeded so Cloud Monitoring alerts fire on partial failures.
#
# `update-all-hands-deck --check-cadence` exits 0 when cadence skips
# (scripts/recess_os.py:337) — non-cadence Mondays are silent successes.
#
# Known: on goals-week Mondays, update-all-hands-deck currently raises
# NotImplementedError (all_hands_deck.py:156-159 — MCP integration not wired).
# This crashes the deck step intentionally → alert fires → matches local-cron behavior.
# Pre-existing bug, out of scope for Batch 6.
# TODO(Task 11 alert policy): suppress alerts that match this specific failure
# shape until the Slides API is wired — otherwise alert fatigue every other
# Monday during paternity will train Jack/Leo to ignore #infra-alerts.
# Document in PATERNITY-RUNBOOK.md as a known false positive.

set +e

echo "[Monday cron] Starting at $(date --iso-8601=seconds)"

echo "[Monday cron] Step 1/2: Monday Pulse"
# 360s = generous buffer over local cron times (~30-60s) for cold start + BQ snapshot read.
timeout --kill-after=15s 360s python /app/scripts/post_monday_pulse.py --post
PULSE_EXIT=$?
[ $PULSE_EXIT -eq 124 ] \
  && echo "[Monday cron] Pulse TIMED OUT (240s)" \
  || echo "[Monday cron] Pulse exit: $PULSE_EXIT"

echo "[Monday cron] Step 2/2: Update All-Hands deck"
timeout --kill-after=15s 240s python /app/scripts/recess_os.py update-all-hands-deck --check-cadence
DECK_EXIT=$?
[ $DECK_EXIT -eq 124 ] \
  && echo "[Monday cron] Deck TIMED OUT (240s)" \
  || echo "[Monday cron] Deck exit: $DECK_EXIT"

if [ $PULSE_EXIT -ne 0 ] || [ $DECK_EXIT -ne 0 ]; then
  echo "[Monday cron] PARTIAL FAILURE: pulse=$PULSE_EXIT deck=$DECK_EXIT"
  exit 1
fi

echo "[Monday cron] All steps succeeded"
exit 0
