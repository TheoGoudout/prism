#!/usr/bin/env bash
# Resolve the ref to a commit before Coolify is touched, so a typo'd tag fails
# here instead of leaving production pinned to a ref that does not exist.
#
# GH_TOKEN, REF and REPOSITORY come from the calling step's env.
set -euo pipefail

if ! SHA=$(gh api "repos/${REPOSITORY}/commits/${REF}" --jq .sha 2>/dev/null); then
  echo "::error::Ref '${REF}' does not exist in ${REPOSITORY}."
  exit 1
fi

echo "sha=$SHA" >> "$GITHUB_OUTPUT"
echo "Deploying ${REF} (${SHA})."
