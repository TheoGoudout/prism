#!/usr/bin/env bash
# Block until Coolify reports the build finished, failed, or ran out of time.
#
# COOLIFY_URL, COOLIFY_API_TOKEN and DEPLOYMENT_UUID come from the calling step's
# env.
set -euo pipefail
# shellcheck source=.github/scripts/lib/coolify.sh
source .github/scripts/lib/coolify.sh

# 30 minutes at 10s intervals, comfortably inside the job timeout so a stuck
# build reports as a timed-out deploy rather than a killed job.
for _ in $(seq 1 180); do
  coolify_call GET "/api/v1/deployments/${DEPLOYMENT_UUID}"

  # A 4xx here means the endpoint or the uuid is wrong — no amount of waiting
  # fixes that, and spinning for the full 30 minutes would bury the real cause.
  # Transport errors and 5xx are worth retrying.
  if [ "$COOLIFY_CODE" -ge 400 ] && [ "$COOLIFY_CODE" -lt 500 ]; then
    echo "::error::Polling /api/v1/deployments/${DEPLOYMENT_UUID} returned HTTP ${COOLIFY_CODE}." \
      "Check the Coolify API version — the deployment endpoint may have moved."
    printf '%s\n' "$COOLIFY_BODY"
    exit 1
  fi

  STATUS=$(printf '%s' "$COOLIFY_BODY" | jq -r '.status // empty' 2>/dev/null || true)

  case "$STATUS" in
    finished | success)
      echo "Build finished."
      exit 0
      ;;
    failed | error | cancelled-by-user)
      echo "::error::Coolify deployment ${DEPLOYMENT_UUID} ended as '${STATUS}'."
      printf '%s\n' "$COOLIFY_BODY"
      exit 1
      ;;
    "") echo "No status yet, retrying." ;;
    *) echo "Status: ${STATUS}" ;;
  esac
  sleep 10
done

echo "::error::Coolify deployment ${DEPLOYMENT_UUID} did not finish within 30 minutes."
exit 1
