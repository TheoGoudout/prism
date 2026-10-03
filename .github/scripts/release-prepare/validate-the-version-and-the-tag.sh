#!/usr/bin/env bash
# Refuse a version that is malformed, already taken, or going backwards.
#
# VERSION, TAG and GH_TOKEN come from the calling step's env.
set -euo pipefail

# The format is defined once, in scripts/set-version.mjs.
bun scripts/set-version.mjs --validate "$VERSION" >/dev/null

if git rev-parse -q --verify "refs/tags/${TAG}" >/dev/null; then
  echo "::error::Tag ${TAG} already exists."
  exit 1
fi

# A draft release also reserves the tag name; creating a second one would
# silently produce two drafts racing for the same tag.
if gh release view "$TAG" >/dev/null 2>&1; then
  echo "::error::A release (possibly a draft) already exists for ${TAG}."
  exit 1
fi

# Guard against going backwards. Deliberately not `sort -V`, which ranks
# 1.5.0-rc2 above 1.5.0 and would reject every rc promotion.
bun scripts/set-version.mjs --is-newer "$VERSION"
