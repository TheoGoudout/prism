# Coolify API helpers. Sourced, never executed.
#
# Every call to Coolify is the same three moves: append the path to a base URL
# with any trailing slash removed, send it with the bearer token, and split the
# HTTP status off the end of the body. Each of the four steps in
# deploy-coolify.yml had written that out again, which is three chances for the
# `-w '\n%{http_code}'` / `tail -n1` / `sed '$d'` pair to disagree with itself.
#
# COOLIFY_URL and COOLIFY_API_TOKEN come from the calling step's env.
#
# After coolify_call, two variables hold the result:
#   COOLIFY_CODE   the HTTP status, or 000 when curl itself failed
#   COOLIFY_BODY   everything before it

# shellcheck shell=bash

coolify_call() {
  local method=$1 path=$2 data=${3:-}
  local base="${COOLIFY_URL%/}"
  local response

  local -a args=(
    -sS -w '\n%{http_code}' -X "$method" "${base}${path}"
    -H "Authorization: Bearer ${COOLIFY_API_TOKEN}"
    -H "Content-Type: application/json"
  )
  [ -n "$data" ] && args+=(-d "$data")

  # A transport failure has no status line to split, so give it one rather than
  # letting `tail -n1` return part of an error message and `[ "$CODE" -lt 200 ]`
  # fail on a non-integer.
  response=$(curl "${args[@]}") || response=$'\n000'

  COOLIFY_CODE=$(printf '%s' "$response" | tail -n1)
  COOLIFY_BODY=$(printf '%s' "$response" | sed '$d')
}

# Fail the step unless the last call returned 2xx. The argument is the thing
# being attempted, phrased to complete "Coolify refused to …".
coolify_require_ok() {
  if [ "$COOLIFY_CODE" -lt 200 ] || [ "$COOLIFY_CODE" -ge 300 ]; then
    echo "::error::Coolify refused to $1 (HTTP ${COOLIFY_CODE})."
    printf '%s\n' "$COOLIFY_BODY"
    exit 1
  fi
}
