"""Minimal JSON-over-HTTP helpers for the platform APIs."""

from typing import Any

import httpx

_TIMEOUT_SECONDS = 15


def _json(resp: httpx.Response) -> dict[str, Any]:
    resp.raise_for_status()
    data: dict[str, Any] = resp.json()
    return data


def _headers(token: str | None, headers: dict[str, str] | None) -> dict[str, str]:
    auth = {"Authorization": f"Bearer {token}"} if token else {}
    return {**auth, **(headers or {})}


def get_json(
    url: str,
    *,
    token: str | None = None,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    """GET a JSON API (with a Bearer token if given); raise on HTTP errors."""
    resp = httpx.get(
        url,
        params=params,
        headers=_headers(token, headers),
        timeout=_TIMEOUT_SECONDS,
    )
    return _json(resp)


def post_json(
    url: str,
    *,
    token: str | None = None,
    body: dict[str, Any] | None = None,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """POST a JSON body (with a Bearer token if given); raise on HTTP errors."""
    resp = httpx.post(
        url,
        json=body,
        params=params,
        headers=_headers(token, None),
        timeout=_TIMEOUT_SECONDS,
    )
    return _json(resp)
