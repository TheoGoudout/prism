#!/usr/bin/env bash
# Prove the API is up behind Coolify's proxy, and serving the version this run
# asked for.
#
# The deploy reporting success is not the same claim: Coolify reports on its
# own build, not on what the proxy ends up routing to.
#
# API_URL and EXPECTED come from the calling step's env.
set -euo pipefail

BASE="${API_URL%/}"
URL="${BASE}/api/v1/utils/health-check/"

# `importlib.metadata` hands back PEP 440-normalised versions, so a 1.5.0-rc1
# in pyproject.toml is reported as 1.5.0rc1. Compare with the separators removed
# rather than literally. `--` matters: without it tr reads the leading `-` of
# the delete set as an option, fails, and returns empty for *both* sides —
# which would make the comparison pass unconditionally.
normalise() { printf '%s' "$1" | tr -d -- '-_' | tr '[:upper:]' '[:lower:]'; }

# The containers need a moment to come up behind the proxy even once the build
# reports finished: prestart runs the migrations first.
for _ in $(seq 1 30); do
  if curl -fsS --max-time 10 "$URL" >/dev/null; then
    HEALTHY=1
    break
  fi
  sleep 10
done

if [ "${HEALTHY:-0}" != "1" ]; then
  echo "::error::${URL} never came back healthy."
  exit 1
fi

# app/main.py builds the FastAPI app with the installed package's version, i.e.
# backend/pyproject.toml at the deployed ref.
LIVE=$(curl -fsS --max-time 10 "${BASE}/api/v1/openapi.json" | jq -r '.info.version')

if [ "$(normalise "$LIVE")" != "$(normalise "$EXPECTED")" ]; then
  echo "::error::${BASE} reports version '${LIVE}', expected '${EXPECTED}'." \
    "The deploy reported success but is not serving the requested ref."
  exit 1
fi

echo "live=$LIVE" >> "$GITHUB_OUTPUT"
echo "${BASE} is healthy and serving ${LIVE}."
