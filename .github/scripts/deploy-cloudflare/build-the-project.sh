#!/usr/bin/env bash
# Build one project for one environment.
#
# The API URL normally comes from the committed <project>/.env.<environment>.
# The environment's API_URL variable, when set, overrides it: Vite lets an
# inline VITE_* variable win over its .env files. It is exported only when
# non-empty, since an empty one would win too and build against no API.
#
# PROJECT, ENVIRONMENT and API_URL come from the calling step's env.
set -euo pipefail

if [ -n "${API_URL:-}" ]; then
  export VITE_API_URL="$API_URL"
  echo "Building ${PROJECT} (${ENVIRONMENT}) against ${API_URL}, from the API_URL variable."
fi

bun run --filter "${PROJECT}" "build:${ENVIRONMENT}"
