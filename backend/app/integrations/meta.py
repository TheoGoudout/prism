"""Shared constants for Meta (Facebook / Instagram) Graph API access."""

# Pinned Graph API version. Meta supports each version for ~2 years; see
# https://developers.facebook.com/docs/graph-api/changelog/versions/
GRAPH_API_VERSION = "v25.0"
GRAPH_API = f"https://graph.facebook.com/{GRAPH_API_VERSION}"
FACEBOOK_DIALOG_URL = f"https://www.facebook.com/{GRAPH_API_VERSION}/dialog/oauth"
