"""Instagram Business OAuth2 provider (shares the Facebook/Meta Graph API app)."""

from app.integrations.meta import graph_get
from app.integrations.oauth.base import AccountInfo
from app.integrations.oauth.facebook import FacebookOAuthProvider
from app.models.integration import Platform


class InstagramOAuthProvider(FacebookOAuthProvider):
    """
    Instagram Business accounts are accessed through the Facebook Graph API.
    The OAuth app and token lifecycle are the same; only the scopes and the
    account lookup differ.
    """

    PLATFORM = Platform.instagram
    SCOPES = [
        "instagram_basic",
        "instagram_manage_insights",
        "pages_show_list",
        "pages_read_engagement",
    ]

    def grant_owner_id(self, *, access_token: str, external_account_id: str) -> str:
        # The account id is the Instagram account's; the grant is the
        # Facebook user's, shared with that user's Facebook integrations
        return str(graph_get("me", access_token, {"fields": "id"})["id"])

    def get_account_info(self, access_token: str) -> AccountInfo:
        # Find the Instagram Business account linked to one of the user's Pages
        data = graph_get(
            "me/accounts",
            access_token,
            {
                "fields": "instagram_business_account{id,name,username,profile_picture_url}"
            },
        )
        for page in data.get("data", []):
            ig = page.get("instagram_business_account")
            if ig:
                return AccountInfo(
                    external_id=ig["id"],
                    name=ig.get("name") or ig.get("username") or "Instagram Account",
                    avatar_url=ig.get("profile_picture_url"),
                )
        raise ValueError(
            "No Instagram Business account is linked to your Facebook Pages"
        )


instagram_provider = InstagramOAuthProvider()
