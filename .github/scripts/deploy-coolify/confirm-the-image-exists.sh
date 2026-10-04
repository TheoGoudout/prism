#!/usr/bin/env bash
# Resolve the image this deploy runs, and prove the Coolify host can pull it.
#
# Checked anonymously, on purpose: the host pulls without credentials, so an
# image only a logged-in client can see would pass a logged-in check here and
# then fail on the host, mid-deploy.
#
# SHA, IMAGE_TAG, OWNER and REF come from the calling step's env. IMAGE_TAG is
# empty unless a caller (images.yml) names the tag it has just published.
set -euo pipefail

TAG="${IMAGE_TAG:-sha-${SHA:0:7}}"
IMAGE="ghcr.io/${OWNER,,}/prism-backend:${TAG}"

if ! docker buildx imagetools inspect "$IMAGE" >/dev/null 2>&1; then
  echo "::error::${IMAGE} cannot be pulled anonymously. Either ${REF} was never" \
    "built — dispatch the 'Backend image' workflow (images.yml) with ref ${REF}" \
    "first — or the GHCR package is private: make it public in its package" \
    "settings. See deployment.md."
  exit 1
fi

{
  echo "tag=${TAG}"
  echo "image=${IMAGE}"
} >> "$GITHUB_OUTPUT"

echo "${IMAGE} ✅"
