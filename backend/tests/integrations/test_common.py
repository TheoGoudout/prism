from datetime import UTC, datetime

import pytest

from app.integrations.common import parse_datetime, sum_known


@pytest.mark.parametrize(
    "value",
    [
        "2024-01-15T08:00:00+0000",  # Meta
        "2024-01-15T08:00:00.000Z",  # Twitter
        "2024-01-15T08:00:00+00:00",
    ],
)
def test_parse_datetime_formats(value: str) -> None:
    assert parse_datetime(value) == datetime(2024, 1, 15, 8, tzinfo=UTC)


@pytest.mark.parametrize("value", [None, "", "not a date", 123])
def test_parse_datetime_invalid(value: object) -> None:
    assert parse_datetime(value) is None


def test_sum_known() -> None:
    assert sum_known(1, None, 2) == 3
    assert sum_known(None, None) is None
    assert sum_known(0) == 0
