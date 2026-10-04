#!/usr/bin/env bash
# Write this version's notes from the pull requests merged since the last
# stable release: into release-notes.md, and into the file the draft release
# is created from.
#
# VERSION, BODY_FILE and GH_TOKEN come from the calling step's env;
# GITHUB_REPOSITORY is the runner's.
set -euo pipefail

python3 scripts/release_notes.py "$VERSION" --body-file "$BODY_FILE"
echo "--- generated notes ---"
cat "$BODY_FILE"
