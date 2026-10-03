#!/usr/bin/env bash
# Work out the version this release will carry, and publish it as step outputs.
#
# The arithmetic itself lives in scripts/set-version.mjs, beside the parser that
# writes the version files, so there is one definition of the version format.
#
# BUMP and EXPLICIT come from the calling step's env.
set -euo pipefail

CURRENT=$(bun scripts/set-version.mjs --print)
echo "Current version: ${CURRENT}"

NEXT=$(bun scripts/set-version.mjs --next "$BUMP" "$EXPLICIT")
echo "Next version: ${NEXT}"

{
  echo "version=$NEXT"
  echo "tag=v$NEXT"
} >> "$GITHUB_OUTPUT"

if echo "$NEXT" | grep -q -- '-rc'; then
  echo "prerelease=true" >> "$GITHUB_OUTPUT"
else
  echo "prerelease=false" >> "$GITHUB_OUTPUT"
fi
