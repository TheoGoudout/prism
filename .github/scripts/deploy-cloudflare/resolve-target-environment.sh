#!/usr/bin/env bash
# Decide which environment this run deploys to, and refuse anything else.
#
# Every caller names one: workflow_call and workflow_dispatch both require it.
# There is no default, because the one this used to have (staging, for the push
# trigger this workflow no longer has) would silently stand in for a missing
# input on a production call. Validating it here
# rather than trusting it downstream matters because the value goes on to select
# a GitHub environment and a wrangler --env: a typo would otherwise deploy the
# staging build to a Worker environment that does not exist, or worse, resolve
# to the top-level (production) configuration.
#
# INPUT_ENVIRONMENT comes from the calling step's env.
set -euo pipefail

ENVIRONMENT="${INPUT_ENVIRONMENT:-}"
case "$ENVIRONMENT" in
  staging | production) ;;
  *)
    echo "::error::Unknown environment '$ENVIRONMENT'."
    exit 1
    ;;
esac

echo "environment=$ENVIRONMENT" >> "$GITHUB_OUTPUT"
echo "Deploying to $ENVIRONMENT"
