from datetime import UTC, datetime

import pytest

from app.migrate.files.reading import (
    day_first_order,
    decode,
    parse_count,
    parse_datetime,
)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("1234", 1234),
        ("1,234", 1234),
        ("1 234", 1234),
        ("1 234", 1234),
        ("1.234", 1234),
        ("1.234.567", 1234567),
        ("1,234.6", 1235),
        ("1.234,6", 1235),
        ("12.0", 12),
        ("3,5", 4),
        ("1.2K", 1200),
        ("2m", 2_000_000),
        ("-15", -15),
        ("", None),
        ("-", None),
        ("N/A", None),
        ("4.5%", None),
    ],
)
def test_parse_count(value: str, expected: int | None) -> None:
    assert parse_count(value) == expected


def test_parse_count_rejects_text() -> None:
    with pytest.raises(ValueError, match="not a number"):
        parse_count("lots")


@pytest.mark.parametrize(
    ("value", "day_first", "expected"),
    [
        ("2024-03-01", False, datetime(2024, 3, 1, tzinfo=UTC)),
        ("2024-03-01 14:30:00", False, datetime(2024, 3, 1, 14, 30, tzinfo=UTC)),
        ("2024-03-01T14:30:00Z", False, datetime(2024, 3, 1, 14, 30, tzinfo=UTC)),
        (
            "2024-03-01T14:30:00+02:00",
            False,
            datetime(2024, 3, 1, 12, 30, tzinfo=UTC),
        ),
        ("2024-03-01 14:30 UTC", False, datetime(2024, 3, 1, 14, 30, tzinfo=UTC)),
        ("03/01/2024", False, datetime(2024, 3, 1, tzinfo=UTC)),
        ("03/01/2024", True, datetime(2024, 1, 3, tzinfo=UTC)),
        ("3/1/24 2:05 pm", False, datetime(2024, 3, 1, 14, 5, tzinfo=UTC)),
        ("01.03.2024 09:15", True, datetime(2024, 3, 1, 9, 15, tzinfo=UTC)),
        ("2024/03/01 12:00 AM", False, datetime(2024, 3, 1, 0, 0, tzinfo=UTC)),
        ("Mar 1, 2024 2:30 PM", False, datetime(2024, 3, 1, 14, 30, tzinfo=UTC)),
        ("Friday, March 1, 2024", False, datetime(2024, 3, 1, tzinfo=UTC)),
        ("1 March 2024 14:30", True, datetime(2024, 3, 1, 14, 30, tzinfo=UTC)),
        ("March 1st, 2024 at 2:30pm", False, datetime(2024, 3, 1, 14, 30, tzinfo=UTC)),
    ],
)
def test_parse_datetime(value: str, day_first: bool, expected: datetime) -> None:
    assert parse_datetime(value, day_first=day_first) == expected


@pytest.mark.parametrize("value", ["", "Total", "31/31/2024"])
def test_parse_datetime_rejects_non_dates(value: str) -> None:
    with pytest.raises(ValueError):
        parse_datetime(value, day_first=False)


def test_day_first_order() -> None:
    assert day_first_order(["01/02/2024", "25/02/2024"]) is True
    assert day_first_order(["01/02/2024", "02/25/2024"]) is False
    assert day_first_order(["01/02/2024", "2024-02-25"]) is None


def test_decode() -> None:
    assert decode("﻿Date,Likes".encode()) == "Date,Likes"
    assert decode("Date\tLikes".encode("utf-16")) == "Date\tLikes"
    assert decode("Café".encode("cp1252")) == "Café"
