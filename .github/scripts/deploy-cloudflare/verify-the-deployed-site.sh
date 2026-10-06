#!/usr/bin/env bash
# Prove the Worker that was just deployed is actually serving.
#
# wrangler reports on its own upload, not on what the zone routes — and the
# custom domains here are attached by hand in the Cloudflare dashboard rather
# than declared in wrangler.jsonc (see the comment in each project's config), so
# "deployed" and "reachable" are genuinely two claims. deploy-coolify.yml
# asserts both about the API; this is the same assertion for the static sites.
#
# PROJECT, ENVIRONMENT and HAS_CLOUDFLARE come from the calling step's env;
# APP_URL and LANDING_URL, when set, are the environment's variables of the same
# name and replace the frontend's and the landing page's default host below.
set -euo pipefail

if [ "$HAS_CLOUDFLARE" != "true" ]; then
  echo "No Cloudflare credentials, so nothing was deployed to check."
  exit 0
fi

case "$PROJECT" in
  frontend) OVERRIDE=${APP_URL:-} ;;
  landing) OVERRIDE=${LANDING_URL:-} ;;
  *) OVERRIDE="" ;;
esac

if [ -n "$OVERRIDE" ]; then
  HOST=${OVERRIDE#https://}
  HOST=${HOST%/}
else
  case "${PROJECT}/${ENVIRONMENT}" in
    frontend/production) HOST="app.prism.ai" ;;
    frontend/staging) HOST="app.staging.prism.ai" ;;
    landing/production) HOST="prism.ai" ;;
    landing/staging) HOST="staging.prism.ai" ;;
    *)
      echo "::error::No hostname known for ${PROJECT} in ${ENVIRONMENT}."
      exit 1
      ;;
  esac
fi

# Cloudflare propagates a new version across the edge in seconds, but not
# instantly, and a cold DNS answer can lag it. Six tries at 10s is generous
# without being a place a broken deploy can hide for long.
for _ in $(seq 1 6); do
  CODE=$(curl -sS -o /dev/null -w '%{http_code}' --max-time 10 "https://${HOST}/" || echo 000)
  if [ "$CODE" = "200" ]; then
    echo "https://${HOST}/ is serving (HTTP 200)."
    exit 0
  fi
  echo "https://${HOST}/ answered ${CODE}, retrying."
  sleep 10
done

echo "::error::https://${HOST}/ never returned 200 after the ${PROJECT} deploy." \
  "The upload succeeded, so check the Worker's routes and its runtime logs."
exit 1
