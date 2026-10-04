#!/usr/bin/env bash
# Land the version bump on master, and report the commit it landed as.
#
# The tag is not created here: GitHub creates it when the draft release is
# published, which is what makes a tag without a release impossible.
#
# VERSION comes from the calling step's env.
set -euo pipefail

git config user.name "github-actions[bot]"
git config user.email "github-actions[bot]@users.noreply.github.com"
git add -A
git commit -m "chore(release): ${VERSION}"
git push origin HEAD:master

echo "sha=$(git rev-parse HEAD)" >> "$GITHUB_OUTPUT"
