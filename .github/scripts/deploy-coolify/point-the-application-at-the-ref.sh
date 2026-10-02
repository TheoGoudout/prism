#!/usr/bin/env bash
# Re-pin the Coolify application to the ref this run deploys.
#
# COOLIFY_URL, COOLIFY_API_TOKEN, COOLIFY_APP_UUID and REF come from the calling
# step's env.
set -euo pipefail
# shellcheck source=.github/scripts/lib/coolify.sh
source .github/scripts/lib/coolify.sh

# `git_branch` is Coolify's field for "the ref to check out"; it holds a tag
# name just as happily as a branch name, which is how production was pinned by
# hand before this workflow existed.
coolify_call PATCH "/api/v1/applications/${COOLIFY_APP_UUID}" \
  "$(jq -cn --arg ref "$REF" '{git_branch: $ref}')"
coolify_require_ok "re-pin the application"

echo "Application pinned to ${REF}."
