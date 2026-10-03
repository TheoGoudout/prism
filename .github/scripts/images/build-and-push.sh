#!/usr/bin/env bash
# Build backend/Dockerfile for amd64 and push every tag resolved for it.
#
# The context is the repository root: the backend resolves the uv workspace from
# the root pyproject.toml and uv.lock. The source label links the GHCR package
# to this repository, so it shows on the repository page and inherits its
# access settings.
#
# GH_TOKEN, TAGS (newline-separated) and SHA come from the calling step's env.
set -euo pipefail

echo "$GH_TOKEN" | docker login ghcr.io -u "$GITHUB_ACTOR" --password-stdin

args=()
while IFS= read -r tag; do
  [ -n "$tag" ] && args+=(--tag "$tag")
done <<< "$TAGS"

docker build \
  --platform linux/amd64 \
  --file backend/Dockerfile \
  --label "org.opencontainers.image.source=${GITHUB_SERVER_URL}/${GITHUB_REPOSITORY}" \
  --label "org.opencontainers.image.revision=${SHA}" \
  "${args[@]}" \
  .

while IFS= read -r tag; do
  [ -n "$tag" ] && docker push "$tag"
done <<< "$TAGS"
