#!/usr/bin/env bash
# Start the deployment, and publish its uuid so the next step can poll it.
#
# COOLIFY_URL, COOLIFY_API_TOKEN, COOLIFY_APP_UUID and FORCE come from the
# calling step's env.
set -euo pipefail
# shellcheck source=.github/scripts/lib/coolify.sh
source .github/scripts/lib/coolify.sh

# `force` has to reach Coolify as a real JSON boolean. Sent as the string
# "false" it is truthy on the far side, which silently turns every deploy into a
# cache-less rebuild.
case "${FORCE:-false}" in
  true | True | TRUE) FORCE_JSON=true ;;
  *) FORCE_JSON=false ;;
esac

# Coolify 4.2 made every state-changing endpoint POST-only; the GET form this
# used to send now answers `405 This endpoint has changed to a POST request.`
# and the release never reaches production.
#
# The parameters go in both the query string and the JSON body on purpose: which
# of the two the deploy controller reads has moved around across Coolify
# versions, and sending consistent values in both is free insurance against
# picking the wrong one.
coolify_call POST "/api/v1/deploy?uuid=${COOLIFY_APP_UUID}&force=${FORCE_JSON}" \
  "$(jq -cn --arg uuid "$COOLIFY_APP_UUID" --argjson force "$FORCE_JSON" \
    '{uuid: $uuid, force: $force}')"

if [ "$COOLIFY_CODE" = "405" ]; then
  echo "::error::Coolify rejected the deploy method (HTTP 405). The API contract" \
    "for /api/v1/deploy has moved again — check the Coolify release notes for" \
    "the method this version expects."
  printf '%s\n' "$COOLIFY_BODY"
  exit 1
fi

coolify_require_ok "start a deployment"

# Response shape has moved around across Coolify versions, so accept either the
# array form or a bare object and treat "no uuid" as "started but not trackable"
# rather than as a failure.
UUID=$(printf '%s' "$COOLIFY_BODY" \
  | jq -r '(.deployments[0].deployment_uuid // .deployment_uuid // empty)' 2>/dev/null || true)

if [ -z "$UUID" ]; then
  echo "::warning::Coolify returned no deployment uuid, so build progress cannot" \
    "be polled. Falling back to the health and version checks."
  printf '%s\n' "$COOLIFY_BODY"
else
  echo "Deployment ${UUID} started."
fi

echo "uuid=$UUID" >> "$GITHUB_OUTPUT"
