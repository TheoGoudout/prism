"""Helpers shared by the platform integrations (login and sync)."""

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# How far back each sync looks for daily metrics and recent posts
SYNC_WINDOW_DAYS = 30


def parse_datetime(value: Any) -> datetime | None:
    """Parse an ISO 8601 timestamp (e.g. "…Z" or "…+0000"), or return None."""
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


@contextmanager
def log_http_errors(what: str) -> Iterator[None]:
    """
    Log and swallow an HTTP error, so one failing step (e.g. a page's insights)
    doesn't abort the rest of the sync.
    """
    try:
        yield
    except httpx.HTTPStatusError as exc:
        logger.error("%s failed: %s", what, exc)


def sum_known(*values: Any) -> int | None:
    """Sum of the values the platform reported, or None if it reported none."""
    known = [v for v in values if isinstance(v, int)]
    return sum(known) if known else None
