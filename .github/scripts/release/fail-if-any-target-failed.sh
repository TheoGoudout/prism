#!/usr/bin/env bash
# Make the run's conclusion the release's conclusion.
#
# report.sh above always exits 0, which is right for a report and wrong for the
# last job in the workflow. Skipped is not failed: a narrowed `targets` run
# deliberately skips the rest, and should be able to go green.
#
# The three *_RESULT values come from the calling step's env.
set -euo pipefail

failed=""
for target in "Backend image:${IMAGES_RESULT}" \
  "Coolify production:${COOLIFY_RESULT}" \
  "Cloudflare production:${CLOUDFLARE_RESULT}"; do
  name=${target%%:*}
  result=${target#*:}
  case "$result" in
    failure | cancelled) failed="${failed} ${name}(${result})" ;;
  esac
done

if [ -n "$failed" ]; then
  echo "::error::Release target(s) did not complete:${failed}. Re-run failed jobs" \
    "to retry only those, or use the workflow_dispatch 'targets' input."
  exit 1
fi
