#!/usr/bin/env bash
# Fail the run when the production environment is missing its Coolify secrets.
#
# Checked in a step because these secrets live on the GitHub Environment, and
# environment secrets only resolve inside a job that declares `environment:`.
# A failure rather than a skip: a backend that silently did not deploy is a
# frontend talking to the wrong API.
#
# COOLIFY_URL, COOLIFY_API_TOKEN and COOLIFY_APP_UUID come from the calling
# step's env.
set -euo pipefail

MISSING=""
[ -n "${COOLIFY_URL:-}" ] || MISSING="$MISSING COOLIFY_URL"
[ -n "${COOLIFY_API_TOKEN:-}" ] || MISSING="$MISSING COOLIFY_API_TOKEN"
[ -n "${COOLIFY_APP_UUID:-}" ] || MISSING="$MISSING COOLIFY_APP_UUID"

if [ -n "$MISSING" ]; then
  echo "::error::Missing Coolify secrets on the 'production' environment:${MISSING}. See deployment.md."
  exit 1
fi
