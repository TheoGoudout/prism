#!/usr/bin/env bash
# Decide which release targets this run drives.
#
# `all` on the release trigger, and on a dispatch that did not narrow it.
# Narrowing is for the half-failed release: re-driving the one target that broke
# rather than redeploying all of them.
#
# TARGETS comes from the calling step's env.
set -euo pipefail

for target in coolify cloudflare; do
  if [ "$TARGETS" = "all" ] || [ "$TARGETS" = "$target" ]; then
    echo "$target=true" >> "$GITHUB_OUTPUT"
  else
    echo "$target=false" >> "$GITHUB_OUTPUT"
  fi
done

echo "Targets: ${TARGETS}."
