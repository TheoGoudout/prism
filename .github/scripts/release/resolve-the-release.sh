#!/usr/bin/env bash
# Resolve the tag to deploy and whether it is a pre-release.
#
# Pre-releases never reach production. A manual dispatch names an existing
# release; its pre-release flag is read from GitHub rather than trusted.
#
# GH_TOKEN, TAG and REPOSITORY come from the calling step's env.
set -euo pipefail

if ! PRERELEASE=$(gh api "repos/${REPOSITORY}/releases/tags/${TAG}" --jq .prerelease 2>/dev/null); then
  echo "::error::No published release for tag '${TAG}' in ${REPOSITORY}."
  exit 1
fi

{
  echo "tag=$TAG"
  echo "prerelease=$PRERELEASE"
} >> "$GITHUB_OUTPUT"

if [ "$PRERELEASE" = "true" ]; then
  echo "::notice::${TAG} is a pre-release, so it is not deployed to production."
else
  echo "Releasing ${TAG} to production."
fi
