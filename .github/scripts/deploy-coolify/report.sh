#!/usr/bin/env bash
# Write what this deploy did to the run summary.
#
# ENVIRONMENT, REF, SHA, IMAGE, EXPECTED, LIVE, DEPLOYMENT and API_HOST come from the
# calling step's env, which runs `if: always()` — so several of them are empty
# when the deploy failed before reaching that step.
set -euo pipefail

{
  echo "## Coolify — ${ENVIRONMENT}"
  echo
  echo "| | |"
  echo "| --- | --- |"
  echo "| Ref | \`${REF}\` |"
  echo "| Commit | \`${SHA:-not resolved}\` |"
  echo "| Image | \`${IMAGE:-not resolved}\` |"
  echo "| Expected version | ${EXPECTED:-not resolved} |"
  echo "| Live version | ${LIVE:-not verified} |"
  echo "| Deployment | \`${DEPLOYMENT:-not reported}\` |"
  echo "| API | https://${API_HOST:-unknown} |"
} >> "$GITHUB_STEP_SUMMARY"
