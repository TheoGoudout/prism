#!/usr/bin/env bash
# Open the draft whose publication starts the rollout.
#
# The notes are the ones generate-release-notes.sh wrote into release-notes.md,
# so the draft and the file say the same thing. Review them in the draft before
# publishing.
#
# GH_TOKEN, TAG, SHA, PRERELEASE and BODY_FILE come from the calling step's env.
set -euo pipefail

# --target is the bump commit SHA, not "master", so later pushes cannot move
# where the tag ends up landing.
ARGS=(--draft --target "$SHA" --title "$TAG" --notes-file "$BODY_FILE")
[ "$PRERELEASE" = "true" ] && ARGS+=(--prerelease)

gh release create "$TAG" "${ARGS[@]}"
