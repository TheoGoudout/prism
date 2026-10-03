#!/usr/bin/env bash
# Resolve the ref to a commit, and work out what the deployed API should report.
#
# Done before Coolify is touched, so a typo'd tag fails here instead of leaving
# production pinned to a ref that does not exist.
#
# GH_TOKEN, REF and REPOSITORY come from the calling step's env.
set -euo pipefail

if ! SHA=$(gh api "repos/${REPOSITORY}/commits/${REF}" --jq .sha 2>/dev/null); then
  echo "::error::Ref '${REF}' does not exist in ${REPOSITORY}."
  exit 1
fi

# The version the deployed backend should report. Read from pyproject.toml at
# the target commit rather than parsed out of the tag, so the check also works
# for a ref that is not a release tag. scripts/set-version.mjs treats this file
# as the canonical version, and app/main.py serves it as the OpenAPI version.
PYPROJECT=$(gh api "repos/${REPOSITORY}/contents/backend/pyproject.toml?ref=${SHA}" \
  -H "Accept: application/vnd.github.raw")
VERSION=$(printf '%s\n' "$PYPROJECT" \
  | grep -m1 -E '^version[[:space:]]*=' \
  | sed -E 's/^version[[:space:]]*=[[:space:]]*"([^"]+)".*/\1/')

if [ -z "$VERSION" ]; then
  echo "::error::Could not read a version out of backend/pyproject.toml at ${SHA}."
  exit 1
fi

{
  echo "sha=$SHA"
  echo "version=$VERSION"
} >> "$GITHUB_OUTPUT"
echo "Deploying ${REF} (${SHA}), expecting version ${VERSION}."
