#!/usr/bin/env bash
# Commit whatever the formatting hooks changed and push it back to the PR.
#
# The push goes through the credential the checkout step persisted, which is
# the PRE_COMMIT token: a push made with GITHUB_TOKEN would not trigger CI.
set -euo pipefail

git config user.name "github-actions[bot]"
git config user.email "github-actions[bot]@users.noreply.github.com"
git add -A
if git diff --staged --quiet; then
  echo "No changes to commit"
else
  git commit -m "🎨 Auto format and update with pre-commit"
  git push
fi
