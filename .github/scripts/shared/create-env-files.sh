#!/usr/bin/env bash
# Create .env and frontend/.env from their committed examples.
#
# CI only talks to throwaway containers, so the example settings (and their
# dummy credentials) are fine and need no repository secrets. That also lets
# Dependabot and fork pull requests, which cannot read secrets, run CI.
set -euo pipefail

cp .env.example .env
cp frontend/.env.example frontend/.env
