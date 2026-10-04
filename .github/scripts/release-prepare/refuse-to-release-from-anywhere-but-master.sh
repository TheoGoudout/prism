#!/usr/bin/env bash
# Releases are cut from master, and the bump commit is pushed straight to it.
#
# REF comes from the calling step's env.
set -euo pipefail

if [ "$REF" != "refs/heads/master" ]; then
  echo "::error::Releases must be cut from master, got ${REF}."
  exit 1
fi
