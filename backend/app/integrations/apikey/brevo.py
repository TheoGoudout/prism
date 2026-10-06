"""Brevo (formerly Sendinblue): connected with an API key (v3 API)."""

from typing import Any

import httpx

from app.integrations.apikey.base import ApiKeyProvider, InvalidApiKeyError
from app.integrations.http import get_json
from app.integrations.oauth.base import AccountInfo
from app.models.integration import Platform

BREVO_API = "https://api.brevo.com/v3"


def brevo_get(
    path: str, api_key: str, params: dict[str, Any] | None = None
) -> dict[str, Any]:
    return get_json(f"{BREVO_API}/{path}", params=params, headers={"api-key": api_key})


class BrevoApiKeyProvider(ApiKeyProvider):
    PLATFORM = Platform.brevo

    def get_account_info(self, api_key: str) -> AccountInfo:
        try:
            data = brevo_get("account", api_key)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code in (401, 403):
                raise InvalidApiKeyError("Brevo rejected the API key") from exc
            raise
        return AccountInfo(
            external_id=str(data.get("organization_id") or data["email"]),
            name=data.get("companyName") or data.get("email") or "Brevo",
            avatar_url=None,
        )


brevo_provider = BrevoApiKeyProvider()
