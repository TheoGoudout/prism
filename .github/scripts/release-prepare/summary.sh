#!/usr/bin/env bash
# Say what was done, and what the human still has to press.
#
# TAG, VERSION, SHA and RELEASES_URL come from the calling step's env.
set -euo pipefail

{
  echo "## Draft release ${TAG} is ready"
  echo
  echo "Version bumped to \`${VERSION}\` on master (commit \`${SHA}\`)."
  echo
  echo "**Nothing has been deployed yet, and the tag does not exist yet.**"
  echo
  echo "Review the notes and press *Publish release* at ${RELEASES_URL} to create"
  echo "the tag and deploy it to production (backend first, then the frontend)."
} >> "$GITHUB_STEP_SUMMARY"
