#!/usr/bin/env bash
# Set the application's TAG variable, which compose.yml interpolates into the
# backend image reference. Coolify applies it on the deploy the next step
# triggers.
#
# COOLIFY_URL, COOLIFY_API_TOKEN, COOLIFY_APP_UUID and TAG come from the calling
# step's env.
set -euo pipefail
# shellcheck source=.github/scripts/lib/coolify.sh
source .github/scripts/lib/coolify.sh

coolify_upsert_env TAG "$TAG"

echo "Application set to run image tag ${TAG}."
