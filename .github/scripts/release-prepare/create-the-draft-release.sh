#!/usr/bin/env bash
# Open the draft whose publication starts the rollout.
#
# The notes are GitHub's own, generated from the pull requests merged since the
# last stable release and sorted into sections by their labels — see
# .github/release.yml. Every pull request carries exactly one of those labels
# (labeler.yml's check-labels job), so nothing lands in a catch-all section by
# accident. Review them in the draft before publishing.
#
# GH_TOKEN, TAG, SHA and PRERELEASE come from the calling step's env.
set -euo pipefail

# --target is the bump commit SHA, not "master", so later pushes cannot move
# where the tag ends up landing.
ARGS=(--draft --target "$SHA" --title "$TAG" --generate-notes)
[ "$PRERELEASE" = "true" ] && ARGS+=(--prerelease)

# Notes for a stable release cover everything since the last stable release,
# not only the delta since its own last release candidate. With no stable tag
# yet, GitHub starts from the beginning of the history.
LAST_STABLE=$(git tag --list 'v*' --sort=-v:refname | grep -m1 -E '^v[0-9]+\.[0-9]+\.[0-9]+$' || true)
[ -n "$LAST_STABLE" ] && ARGS+=(--notes-start-tag "$LAST_STABLE")

gh release create "$TAG" "${ARGS[@]}"
