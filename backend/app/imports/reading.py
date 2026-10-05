"""
Reading exported CSV files: encoding, delimiter, the header row, and the
numbers and dates in cells, which every tool formats its own way.
"""

import csv
import io
import re
from datetime import UTC, datetime

# Exports put a title, the account or the date range above the header row
HEADER_SEARCH_ROWS = 20
DELIMITERS = (",", ";", "\t")
EMPTY_VALUES = {"", "-", "--", "–", "—", "n/a", "na", "null", "none", "nan"}


class ImportFileError(ValueError):
    """The file as a whole can't be imported."""


def decode(data: bytes) -> str:
    """Text of the file: UTF-8 (with or without BOM), UTF-16 or Windows-1252."""
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return data.decode("utf-16")
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return data.decode("cp1252", errors="replace")


def read_rows(text: str, delimiter: str) -> list[list[str]]:
    return [
        [cell.strip() for cell in row]
        for row in csv.reader(io.StringIO(text), delimiter=delimiter)
    ]


def candidate_tables(text: str) -> list[list[list[str]]]:
    """The file split with each delimiter that splits it at all."""
    first_lines = "\n".join(text.splitlines()[:HEADER_SEARCH_ROWS])
    tables = [
        read_rows(text, delimiter)
        for delimiter in DELIMITERS
        if delimiter in first_lines
    ]
    return tables or [read_rows(text, ",")]


# ---------------------------------------------------------------------------
# Numbers
# ---------------------------------------------------------------------------

_SPACES = re.compile(r"[\s  ']")
_THOUSANDS_COMMA = re.compile(r"^-?\d{1,3}(,\d{3})+$")
_THOUSANDS_DOT = re.compile(r"^-?\d{1,3}(\.\d{3})+$")
_SUFFIXES = {"k": 1_000, "m": 1_000_000, "b": 1_000_000_000}


def parse_count(value: str) -> int | None:
    """
    A count as exports write it: "1234", "1,234", "1 234", "1.234" (European),
    "1.2K", "12.0". Empty cells and dashes are None; percentages (rates, not
    counts) are ignored.

    Raises ValueError if the cell isn't a number.
    """
    cleaned = _SPACES.sub("", value).lower()
    if cleaned in EMPTY_VALUES or cleaned.endswith("%"):
        return None
    multiplier = 1
    if cleaned[-1:] in _SUFFIXES:
        multiplier = _SUFFIXES[cleaned[-1]]
        cleaned = cleaned[:-1]

    if _THOUSANDS_COMMA.match(cleaned) or _THOUSANDS_DOT.match(cleaned):
        cleaned = cleaned.replace(",", "").replace(".", "")
    elif "," in cleaned and "." in cleaned:
        # The last separator is the decimal one: 1.234,5 or 1,234.5
        if cleaned.rfind(",") > cleaned.rfind("."):
            cleaned = cleaned.replace(".", "").replace(",", ".")
        else:
            cleaned = cleaned.replace(",", "")
    else:
        cleaned = cleaned.replace(",", ".")

    try:
        number = float(cleaned)
    except ValueError:
        raise ValueError(f"'{value}' is not a number") from None
    return round(number * multiplier)


# ---------------------------------------------------------------------------
# Dates
# ---------------------------------------------------------------------------

_NUMERIC_DATE = re.compile(
    r"^(?P<a>\d{1,4})[/.\-](?P<b>\d{1,2})[/.\-](?P<c>\d{2,4})"
    r"(?:[ T,]+(?P<h>\d{1,2}):(?P<m>\d{2})(?::(?P<s>\d{2}))?(?:\.\d+)?"
    r"\s*(?P<ampm>[ap]\.?\s?m\.?)?)?$",
    re.IGNORECASE,
)
_WEEKDAY = re.compile(r"^(mon|tue|wed|thu|fri|sat|sun)[a-z]*\.?,?\s+", re.IGNORECASE)
_TIMEZONE = re.compile(r"\s*\(?\b(utc|gmt|z)\)?$", re.IGNORECASE)
_TEXT_FORMATS = (
    "%b %d %Y %I:%M %p",
    "%b %d %Y %H:%M",
    "%b %d %Y",
    "%B %d %Y %I:%M %p",
    "%B %d %Y %H:%M",
    "%B %d %Y",
    "%d %b %Y %H:%M",
    "%d %b %Y %I:%M %p",
    "%d %b %Y",
    "%d %B %Y %H:%M",
    "%d %B %Y",
)


def day_first_order(values: list[str]) -> bool | None:
    """
    Whether the file's numeric dates read day/month (31/01/2024) or
    month/day (01/31/2024), if any date proves it; None if all are ambiguous.
    """
    for value in values:
        match = _NUMERIC_DATE.match(value.strip())
        if match is None or len(match["a"]) == 4:
            continue
        if int(match["a"]) > 12:
            return True
        if int(match["b"]) > 12:
            return False
    return None


def parse_datetime(value: str, *, day_first: bool) -> datetime:
    """
    A date or timestamp in any of the usual export formats, in UTC (times
    without a timezone are taken as UTC).

    Raises ValueError if the cell isn't a date.
    """
    text = value.strip()
    if not text:
        raise ValueError("the date is missing")
    parsed: datetime | None
    try:
        parsed = datetime.fromisoformat(text.replace(" UTC", "+00:00"))
    except ValueError:
        parsed = _parse_numeric(text, day_first) or _parse_text(text)
    if parsed is None:
        raise ValueError(f"'{value}' is not a date")
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _parse_numeric(text: str, day_first: bool) -> datetime | None:
    match = _NUMERIC_DATE.match(_TIMEZONE.sub("", text))
    if match is None:
        return None
    a, b, c = int(match["a"]), int(match["b"]), int(match["c"])
    if len(match["a"]) == 4:  # 2024/01/31
        year, month, day = a, b, c
    else:
        day, month = (a, b) if day_first else (b, a)
        year = c + 2000 if c < 100 else c
    hour, minute = int(match["h"] or 0), int(match["m"] or 0)
    second = int(match["s"] or 0)
    if match["ampm"]:
        hour = hour % 12 + (12 if match["ampm"].lower().startswith("p") else 0)
    try:
        return datetime(year, month, day, hour, minute, second)
    except ValueError:
        return None


def _parse_text(text: str) -> datetime | None:
    """ "Mar 1, 2024 2:30 PM", "Friday, March 1, 2024", "1 March 2024 14:30"."""
    cleaned = _TIMEZONE.sub("", _WEEKDAY.sub("", text))
    cleaned = re.sub(r"\s+at\s+|,", " ", cleaned)
    cleaned = re.sub(r"(\d)(st|nd|rd|th)\b", r"\1", cleaned)
    cleaned = re.sub(
        r"(?i)([ap])\.?m\.?$", lambda m: m[1].upper() + "M", " ".join(cleaned.split())
    )
    cleaned = re.sub(r"(\d)([AP]M)$", r"\1 \2", cleaned)
    for fmt in _TEXT_FORMATS:
        try:
            return datetime.strptime(cleaned, fmt)
        except ValueError:
            continue
    return None
