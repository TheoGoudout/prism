#!/bin/sh
set -e
# Inject FRONTEND_URL into the HTML template at container startup.
# Single-quoted variable list limits substitution to only ${FRONTEND_URL},
# leaving any other ${...} patterns in the file untouched.
# The single quotes are the point: envsubst takes the *names* it may substitute,
# so expanding them here would pass FRONTEND_URL's own value (usually empty) as
# the allowlist. shellcheck cannot know that, and its directive syntax takes no
# trailing reason, so the reason lives above it.
# shellcheck disable=SC2016
envsubst '${FRONTEND_URL}' \
  < /usr/share/nginx/html/index.html.template \
  > /usr/share/nginx/html/index.html
