#!/usr/bin/env bash
# Write the release's per-target results to the run summary.
#
# TAG and the three *_RESULT values come from the calling step's env, which runs
# `if: always()` — so any of them may be `skipped` or `failure`.
set -euo pipefail

{
  echo "## Release ${TAG}"
  echo
  echo "| Target | Result |"
  echo "| --- | --- |"
  echo "| Backend image | ${IMAGES_RESULT} |"
  echo "| Coolify production (backend) | ${COOLIFY_RESULT} |"
  echo "| Cloudflare production | ${CLOUDFLARE_RESULT} |"
} >> "$GITHUB_STEP_SUMMARY"
