"""What every API migration source provides, and the HTTP client they share."""

import logging
import time
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any, Protocol

import httpx

from app.models.metrics import MetricSnapshotUpsert, PostUpsert
from app.models.migration import RemoteProfile, SourceCredentials

logger = logging.getLogger(__name__)

TIMEOUT_SECONDS = 60
MAX_ATTEMPTS = 4
MAX_RETRY_WAIT_SECONDS = 60


class SourceAuthError(Exception):
    """The source tool rejected the credentials."""


@dataclass
class ProfileData:
    """Everything fetched for one profile."""

    snapshots: list[MetricSnapshotUpsert] = field(default_factory=list)
    posts: list[PostUpsert] = field(default_factory=list)
    # Parts that couldn't be fetched; the rest is still stored
    errors: list[str] = field(default_factory=list)


class Source(Protocol):
    def list_profiles(self, credentials: SourceCredentials) -> list[RemoteProfile]:
        """The profiles the credentials give access to.

        Raises SourceAuthError if the credentials are rejected."""
        ...

    def fetch(
        self,
        credentials: SourceCredentials,
        profile: RemoteProfile,
        date_from: date,
        date_to: date,
    ) -> ProfileData:
        """A profile's daily metrics and posts over the date range."""
        ...


class ApiClient:
    """
    httpx with what bulk exports need: a minimum delay between requests (to
    stay under the tool's rate limit) and retries on rate limits and server
    errors.
    """

    def __init__(
        self,
        base_url: str,
        headers: dict[str, str],
        *,
        min_interval: float = 0.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._client = httpx.Client(
            base_url=base_url,
            headers=headers,
            timeout=TIMEOUT_SECONDS,
            transport=transport,
        )
        self._min_interval = min_interval
        self._last_request = 0.0

    def request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        for attempt in range(1, MAX_ATTEMPTS + 1):
            wait = self._last_request + self._min_interval - time.monotonic()
            if wait > 0:
                time.sleep(wait)
            self._last_request = time.monotonic()
            response = self._client.request(method, url, **kwargs)
            retryable = response.status_code == 429 or response.status_code >= 500
            if not retryable or attempt == MAX_ATTEMPTS:
                break
            delay = _retry_delay(response, attempt)
            logger.info("%s %s: %s, retrying in %ss", method, url, response, delay)
            time.sleep(delay)
        if response.status_code in (401, 403):
            raise SourceAuthError(
                "The credentials were rejected. Check them, and that your plan "
                "includes API access."
            )
        response.raise_for_status()
        return response

    def json(self, method: str, url: str, **kwargs: Any) -> Any:
        return self.request(method, url, **kwargs).json()


def _retry_delay(response: httpx.Response, attempt: int) -> float:
    try:
        delay = float(response.headers.get("Retry-After", ""))
    except ValueError:
        delay = 2.0**attempt
    return min(max(delay, 1.0), MAX_RETRY_WAIT_SECONDS)


def date_windows(date_from: date, date_to: date, days: int) -> list[tuple[date, date]]:
    """[date_from, date_to] split into consecutive windows of at most ``days``."""
    windows = []
    start = date_from
    while start <= date_to:
        end = min(start + timedelta(days=days - 1), date_to)
        windows.append((start, end))
        start = end + timedelta(days=1)
    return windows


def describe_error(exc: Exception) -> str:
    if isinstance(exc, httpx.HTTPStatusError):
        return f"HTTP {exc.response.status_code} from {exc.request.url.path}"
    if isinstance(exc, httpx.HTTPError):
        return f"Network error: {exc}"
    return str(exc)
