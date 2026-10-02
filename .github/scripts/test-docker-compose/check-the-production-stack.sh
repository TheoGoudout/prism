#!/usr/bin/env bash
# Check the production stack does its three jobs, from inside the containers:
# compose.yml publishes no ports, because Coolify's proxy routes to them.
#
# `up --wait` has already waited for the healthchecks (the API's, and the
# worker's `celery inspect ping`); this asserts them again so a failure names
# the service, and covers beat, which has no healthcheck.
set -euo pipefail

compose() { docker compose -f compose.yml "$@"; }

echo "API:"
compose exec -T backend curl -fsS http://localhost:8000/api/v1/utils/health-check/
echo

echo "Worker:"
# Shell-expanded inside the container, where HOSTNAME is the worker's own.
# shellcheck disable=SC2016
compose exec -T celery-worker sh -c \
  'celery -A app.worker.celery_app inspect ping -d "celery@$HOSTNAME" --timeout 10'

echo "Beat:"
if [ -z "$(compose ps --status running -q celery-beat)" ]; then
  echo "::error::celery-beat is not running."
  compose logs celery-beat
  exit 1
fi
echo "running"

# Migrations ran and the first superuser exists: the prestart service is what
# Coolify relies on for both, on every deploy.
echo "Prestart:"
CODE=$(docker inspect -f '{{.State.ExitCode}}' "$(compose ps -a -q prestart)")
if [ "$CODE" != "0" ]; then
  echo "::error::prestart exited with ${CODE}."
  compose logs prestart
  exit 1
fi
echo "completed"
