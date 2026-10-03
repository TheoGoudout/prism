#!/usr/bin/env bash
# Write what this deploy did to the run summary.
#
# REF, SHA, EXPECTED, LIVE, DEPLOYMENT, API_URL and OUTCOME come from the calling step's env,
# which runs `if: always()`, so some are empty when the deploy failed early.
set -euo pipefail

{
  echo "## Coolify — production"
  echo
  echo "| | |"
  echo "| --- | --- |"
  echo "| Ref | \`${REF}\` |"
  echo "| Commit | \`${SHA:-not resolved}\` |"
  echo "| Deployment | \`${DEPLOYMENT:-not reported}\` |"
  echo "| API | ${API_URL} |"
  echo "| Expected version | \`${EXPECTED:-not resolved}\` |"
  echo "| Live version | \`${LIVE:-not reported}\` |"
  echo "| Health and version check | ${OUTCOME:-not run} |"
} >> "$GITHUB_STEP_SUMMARY"
