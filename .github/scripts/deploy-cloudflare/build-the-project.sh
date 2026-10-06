#!/usr/bin/env bash
# Build one project for one environment.
#
# The URL a project points at normally comes from the committed
# <project>/.env.<environment>: the API for the frontend, the app for the
# landing page. The environment's API_URL / APP_URL variable, when set,
# overrides it: Vite lets an inline VITE_* variable win over its .env files, and
# scripts/build-landing.mjs lets an inline FRONTEND_URL win the same way. Each is
# exported only when non-empty, since an empty one would win too and build
# against nothing.
#
# PROJECT, ENVIRONMENT, API_URL and APP_URL come from the calling step's env.
set -euo pipefail

if [ "$PROJECT" = "frontend" ] && [ -n "${API_URL:-}" ]; then
  export VITE_API_URL="$API_URL"
  echo "Building ${PROJECT} (${ENVIRONMENT}) against ${API_URL}, from the API_URL variable."
fi

if [ "$PROJECT" = "landing" ] && [ -n "${APP_URL:-}" ]; then
  export FRONTEND_URL="$APP_URL"
  echo "Building ${PROJECT} (${ENVIRONMENT}) linking to ${APP_URL}, from the APP_URL variable."
fi

bun run --filter "${PROJECT}" "build:${ENVIRONMENT}"
