#!/usr/bin/env bash
# Work out the image name and every tag this build publishes.
#
#   sha-<short>  always — the tag deploys pin, because it never moves
#   <ref>        when the ref is a release tag (v1.8.0), for humans
#   latest       on a push to master only (deploy-staging.yml; a called
#                workflow sees its caller's event)
#
# A registry reference must be lowercase, and github.repository_owner keeps the
# account's casing ("TheoGoudout"), so the owner is lowercased here.
#
# REF and EVENT come from the calling step's env.
set -euo pipefail

IMAGE="ghcr.io/${GITHUB_REPOSITORY_OWNER,,}/prism-backend"
SHA=$(git rev-parse HEAD)
TAG="sha-${SHA:0:7}"

TAGS="${IMAGE}:${TAG}"
if [[ "${REF:-}" =~ ^v[0-9][0-9A-Za-z._-]*$ ]]; then
  TAGS+=$'\n'"${IMAGE}:${REF}"
fi
if [ "$EVENT" = "push" ]; then
  TAGS+=$'\n'"${IMAGE}:latest"
fi

{
  echo "sha=${SHA}"
  echo "tag=${TAG}"
  echo "tags<<EOF"
  echo "$TAGS"
  echo "EOF"
} >> "$GITHUB_OUTPUT"

echo "Publishing:"
echo "$TAGS"
