#!/usr/bin/env bash
# Work out what is being released, and whether it is a pre-release.
#
# GH_TOKEN, TAG and REPOSITORY come from the calling step's env.
set -euo pipefail

if [ -z "$TAG" ]; then
  echo "::error::No tag to release. The release payload was empty and no tag input was given."
  exit 1
fi

# On workflow_dispatch the release payload is absent, so read the pre-release
# flag back from the release itself rather than guessing.
PRERELEASE=$(gh release view "$TAG" --repo "$REPOSITORY" --json isPrerelease --jq .isPrerelease)

# The version format lives in scripts/set-version.mjs, which is what writes it
# into every file carrying it — so that is what validates it here too,
# rather than a third copy of the regex.
VERSION=$(bun scripts/set-version.mjs --validate "${TAG#v}")

{
  echo "tag=$TAG"
  echo "version=$VERSION"
  echo "prerelease=$PRERELEASE"
} >> "$GITHUB_OUTPUT"

echo "Releasing ${TAG} (version ${VERSION}, prerelease=${PRERELEASE})."
