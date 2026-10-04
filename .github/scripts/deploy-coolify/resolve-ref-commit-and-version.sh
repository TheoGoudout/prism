#!/usr/bin/env bash
# Resolve the ref to a commit, and work out what the deployed API should report.
#
# Done through the API rather than a checkout: the only things needed from the
# repository are one commit SHA and one file, and resolving the ref here means a
# typo'd tag fails before Coolify is touched.
#
# GH_TOKEN, REF, REPOSITORY and ENVIRONMENT come from the calling step's env.
set -euo pipefail

if ! SHA=$(gh api "repos/${REPOSITORY}/commits/${REF}" --jq .sha 2>/dev/null); then
  echo "::error::Ref '${REF}' does not exist in ${REPOSITORY}."
  exit 1
fi

# The version the deployed backend should report. Read from pyproject.toml at
# the target commit rather than parsed out of the tag, so the assertion also
# works when the ref is a branch (a staging dispatch of `master`, say).
# `scripts/set-version.mjs` treats this file as the canonical version.
PYPROJECT=$(gh api "repos/${REPOSITORY}/contents/backend/pyproject.toml?ref=${SHA}" \
  -H "Accept: application/vnd.github.raw")
VERSION=$(printf '%s\n' "$PYPROJECT" \
  | grep -m1 -E '^version[[:space:]]*=' \
  | sed -E 's/^version[[:space:]]*=[[:space:]]*"([^"]+)".*/\1/')

if [ -z "$VERSION" ]; then
  echo "::error::Could not read a version out of backend/pyproject.toml at ${SHA}."
  exit 1
fi

case "$ENVIRONMENT" in
  production) API_HOST="api.prism.ai" ;;
  staging) API_HOST="api.staging.prism.ai" ;;
  *)
    echo "::error::Unknown environment '${ENVIRONMENT}'."
    exit 1
    ;;
esac

{
  echo "sha=$SHA"
  echo "version=$VERSION"
  echo "api_host=$API_HOST"
} >> "$GITHUB_OUTPUT"

echo "Deploying ${REF} (${SHA}), expecting version ${VERSION} on ${API_HOST}."
