#!/usr/bin/env bash
# Prove the API is up behind Coolify's proxy.
#
# The deploy reporting success is not the same claim: Coolify reports on its
# own build, not on what the proxy ends up routing to.
#
# API_URL comes from the calling step's env.
set -euo pipefail

URL="${API_URL%/}/api/v1/utils/health-check/"

# The containers need a moment to come up behind the proxy even once the build
# reports finished: prestart runs the migrations first.
for _ in $(seq 1 30); do
  if curl -fsS --max-time 10 "$URL" >/dev/null; then
    echo "${URL} is healthy."
    exit 0
  fi
  sleep 10
done

echo "::error::${URL} never came back healthy."
exit 1
