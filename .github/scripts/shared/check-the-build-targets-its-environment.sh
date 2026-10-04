#!/usr/bin/env bash
# Check a built project carries the URL its environment's committed .env file
# names, and refuse an empty or placeholder one.
#
# Nothing downstream would notice either. Vite substitutes an unset VITE_API_URL
# with the empty string, and a frontend built that way resolves every API call
# against its own Worker — which answers 200 with index.html, because of
# not_found_handling. That is a green deploy of a site broken only at runtime,
# so it is caught here, on the pull request.
#
#   PROJECT      frontend
#   ENVIRONMENT  staging | production
#   API_URL      optional: the environment's API_URL variable, which the build
#                used instead of the committed file
set -euo pipefail

case "$PROJECT" in
  frontend) KEY=VITE_API_URL ;;
  *) echo "::error::Unknown project '${PROJECT}'."; exit 1 ;;
esac

FILE="${PROJECT}/.env.${ENVIRONMENT}"
URL=$(grep "^${KEY}=" "$FILE" | cut -d= -f2- | tr -d '"' || true)
if [ -n "${API_URL:-}" ]; then
  URL=$API_URL
  FILE="the ${ENVIRONMENT} environment's API_URL variable"
fi

if [ -z "$URL" ] || [[ "$URL" == *CHANGEME* ]] || [[ "$URL" != https://* ]]; then
  echo "::error file=${FILE}::${KEY} must be an https:// URL, got '${URL}'."
  exit 1
fi

if ! grep -rqF "$URL" "${PROJECT}/dist"; then
  echo "::error::${PROJECT}/dist does not reference ${URL} (${KEY} from ${FILE})."
  exit 1
fi
echo "${PROJECT} (${ENVIRONMENT}) targets ${URL}"
