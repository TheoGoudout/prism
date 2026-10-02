#!/usr/bin/env bash
# Prove the Worker that was just deployed is serving on its custom domain.
#
# wrangler reports on its own upload, not on what the zone routes, and the
# custom domain is bound by hand in the Cloudflare dashboard (see the comment in
# frontend/wrangler.jsonc), so "deployed" and "reachable" are two claims.
#
# APP_URL comes from the calling step's env.
set -euo pipefail

URL="${APP_URL%/}/"

# A new version reaches the whole edge in seconds, but not instantly.
for _ in $(seq 1 6); do
  CODE=$(curl -sS -o /dev/null -w '%{http_code}' --max-time 10 "$URL" || echo 000)
  if [ "$CODE" = "200" ]; then
    echo "${URL} is serving (HTTP 200)."
    exit 0
  fi
  echo "${URL} answered ${CODE}, retrying."
  sleep 10
done

echo "::error::${URL} never returned 200. The upload succeeded, so check the" \
  "Worker's custom domain binding and its runtime logs."
exit 1
