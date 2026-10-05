"""
Turning an exported CSV into Prism's normalised daily snapshots or posts.
"""

import hashlib
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from app.imports import sources as f
from app.imports.reading import (
    HEADER_SEARCH_ROWS,
    ImportFileError,
    candidate_tables,
    day_first_order,
    decode,
    parse_count,
    parse_datetime,
)
from app.imports.sources import SOURCES, SourceFormat, detect_source, normalise_header
from app.integrations.common import engagement_total
from app.models.imports import ImportKind, ImportSource
from app.models.integration import Platform
from app.models.metrics import ContentType, MetricSnapshotUpsert, PostUpsert

MAX_ROWS = 50_000
# Errors described in the result; the others are only counted
MAX_ERRORS = 20

# How each network is written in a "Network" column, checked in order
_NETWORK_NAMES: tuple[tuple[str, Platform], ...] = (
    ("facebook", Platform.facebook),
    ("instagram", Platform.instagram),
    ("linkedin", Platform.linkedin),
    ("tiktok", Platform.tiktok),
    ("twitter", Platform.twitter),
    ("google analytics", Platform.google_analytics),
)
# Rows some exports add under the data
_SUMMARY_ROWS = {"total", "totals", "sum", "average", "avg", "summary"}
_TWEET_URL = re.compile(r"(?:twitter|x)\.com/[^/]+/status(?:es)?/(\d+)")


@dataclass
class ParsedFile:
    source: ImportSource
    kind: ImportKind
    rows_read: int = 0
    skipped_other_networks: int = 0
    rejected: int = 0
    errors: list[str] = field(default_factory=list)
    snapshots: list[MetricSnapshotUpsert] = field(default_factory=list)
    posts: list[PostUpsert] = field(default_factory=list)

    def reject(self, line: int, message: str) -> None:
        self.rejected += 1
        if len(self.errors) < MAX_ERRORS:
            self.errors.append(f"Line {line}: {message}")


def parse_export(
    data: bytes, *, platform: Platform, source: ImportSource | None = None
) -> ParsedFile:
    """
    Read an export of ``platform``'s data. ``source`` is the tool it comes
    from; it is detected from the headers when not given.

    Raises ImportFileError when no header row with a date and metrics is found.
    """
    table, header_index, columns = _find_header(decode(data), source)
    headers = table[header_index]
    source = source or detect_source(headers)
    fmt = SOURCES[source]
    if not columns:
        columns = _map_columns(headers, fmt)

    kind = (
        ImportKind.posts
        if any(name in columns for name in f.POST_FIELDS)
        else ImportKind.daily_metrics
    )
    rows = [
        (header_index + 2 + offset, row)
        for offset, row in enumerate(table[header_index + 1 :])
        if any(row)
    ]
    if len(rows) > MAX_ROWS:
        raise ImportFileError(f"The file has more than {MAX_ROWS:,} rows")

    parsed = ParsedFile(source=source, kind=kind, rows_read=len(rows))
    _check_single_profile(rows, columns, platform)

    dates = [_cell(row, columns, f.DATE) for _, row in rows]
    order = day_first_order(dates)
    day_first = fmt.day_first if order is None else order

    for line, row in rows:
        if normalise_header(_cell(row, columns, f.DATE)) in _SUMMARY_ROWS:
            parsed.rows_read -= 1
            continue
        network = _cell(row, columns, f.NETWORK)
        if network and _network_platform(network) not in (None, platform):
            parsed.skipped_other_networks += 1
            continue
        try:
            if kind is ImportKind.posts:
                parsed.posts.append(_post(row, columns, platform, day_first))
            else:
                parsed.snapshots.append(_snapshot(row, columns, day_first))
        except ValueError as exc:
            parsed.reject(line, str(exc))
    return parsed


def date_range(parsed: ParsedFile) -> tuple[date | None, date | None]:
    days = [s.date for s in parsed.snapshots] + [
        p.published_at.date() for p in parsed.posts
    ]
    return (min(days), max(days)) if days else (None, None)


# ---------------------------------------------------------------------------
# Header row and columns
# ---------------------------------------------------------------------------


def _map_columns(headers: list[str], fmt: SourceFormat) -> dict[str, int]:
    """Canonical field → column index. A column maps onto one field at most."""
    normalised = [normalise_header(h) for h in headers]
    columns: dict[str, int] = {}
    used: set[int] = set()
    names = (
        [f.DATE, f.TIME, f.POST_ID, f.PERMALINK, f.TEXT, f.MEDIA_URL]
        + [f.CONTENT_TYPE, f.NETWORK, f.PROFILE]
        + list(f.CONTENT_METRICS)
        + list(f.ACCOUNT_METRICS)
    )
    for name in names:
        for alias in fmt.aliases_for(name):
            index = next(
                (i for i, h in enumerate(normalised) if h == alias and i not in used),
                None,
            )
            if index is not None:
                columns[name] = index
                used.add(index)
                break
    return columns


def _is_usable(columns: dict[str, int]) -> bool:
    metrics = f.CONTENT_METRICS + f.ACCOUNT_METRICS
    return f.DATE in columns and any(name in columns for name in metrics)


def _find_header(
    text: str, source: ImportSource | None
) -> tuple[list[list[str]], int, dict[str, int]]:
    """
    The table and its header row: among the first rows, with any delimiter,
    the one that maps the most columns, provided it has a date and a metric.
    """
    best: tuple[int, list[list[str]], int, dict[str, int]] | None = None
    for table in candidate_tables(text):
        for index, row in enumerate(table[:HEADER_SEARCH_ROWS]):
            fmt = SOURCES[source or detect_source(row)]
            columns = _map_columns(row, fmt)
            if _is_usable(columns) and (best is None or len(columns) > best[0]):
                best = (len(columns), table, index, columns)
    if best is None:
        raise ImportFileError(
            "No header row with a date column and metric columns (impressions, "
            "likes, followers…) was found. Export the report as CSV and try again."
        )
    _, table, index, columns = best
    return table, index, columns


def _cell(row: list[str], columns: dict[str, int], name: str) -> str:
    index = columns.get(name)
    if index is None or index >= len(row):
        return ""
    return row[index]


def _network_platform(value: str) -> Platform | None:
    """The platform a "Network" cell names, or None if it isn't one Prism knows."""
    name = normalise_header(value)
    for keyword, platform in _NETWORK_NAMES:
        if keyword in name:
            return platform
    if name == "x" or name.startswith("x "):
        return Platform.twitter
    return None


def _check_single_profile(
    rows: list[tuple[int, list[str]]], columns: dict[str, int], platform: Platform
) -> None:
    """An export covering several profiles of the network can't go to one account."""
    if f.PROFILE not in columns:
        return
    profiles = {
        _cell(row, columns, f.PROFILE)
        for _, row in rows
        if _network_platform(_cell(row, columns, f.NETWORK)) in (None, platform)
    } - {""}
    if len(profiles) > 1:
        raise ImportFileError(
            "The file covers several profiles ("
            + ", ".join(sorted(profiles)[:5])
            + "). Export one profile at a time."
        )


# ---------------------------------------------------------------------------
# Rows
# ---------------------------------------------------------------------------


def _metric(row: list[str], columns: dict[str, int], name: str) -> int | None:
    try:
        return parse_count(_cell(row, columns, name))
    except ValueError as exc:
        raise ValueError(f"{name.replace('_', ' ')}: {exc}") from None


def _content_metrics(row: list[str], columns: dict[str, int]) -> dict[str, Any]:
    values = {name: _metric(row, columns, name) for name in f.CONTENT_METRICS}
    # Prism's engagements are the same sum on every platform (see
    # engagement_total), while tools often count clicks in theirs: recompute
    # it when the file has the main parts, else keep the tool's figure.
    total = engagement_total(
        values[f.LIKES], values[f.COMMENTS], values[f.SHARES], values[f.SAVES]
    )
    has_parts = f.LIKES in columns and f.COMMENTS in columns
    if total is not None and (has_parts or values[f.ENGAGEMENTS] is None):
        values[f.ENGAGEMENTS] = total
    return values


def _when(row: list[str], columns: dict[str, int], day_first: bool) -> datetime:
    value = _cell(row, columns, f.DATE)
    time = _cell(row, columns, f.TIME)
    if time:
        try:
            return parse_datetime(f"{value} {time}", day_first=day_first)
        except ValueError:
            pass
    return parse_datetime(value, day_first=day_first)


def _snapshot(
    row: list[str], columns: dict[str, int], day_first: bool
) -> MetricSnapshotUpsert:
    lost = _metric(row, columns, f.FOLLOWERS_LOST)
    return MetricSnapshotUpsert(
        date=_when(row, columns, day_first).date(),
        **_content_metrics(row, columns),
        followers_count=_metric(row, columns, f.FOLLOWERS_COUNT),
        followers_gained=_metric(row, columns, f.FOLLOWERS_GAINED),
        # Some tools write losses as negative numbers
        followers_lost=abs(lost) if lost is not None else None,
        posts_count=_metric(row, columns, f.POSTS_COUNT),
    )


def _post(
    row: list[str], columns: dict[str, int], platform: Platform, day_first: bool
) -> PostUpsert:
    published_at = _when(row, columns, day_first)
    text = _cell(row, columns, f.TEXT) or None
    permalink = _cell(row, columns, f.PERMALINK) or None
    if permalink and not permalink.startswith(("http://", "https://")):
        permalink = None
    media_url = _cell(row, columns, f.MEDIA_URL) or None
    if media_url and not media_url.startswith(("http://", "https://")):
        media_url = None
    return PostUpsert(
        external_id=_external_id(
            _cell(row, columns, f.POST_ID), permalink, published_at.isoformat(), text
        ),
        content_type=_content_type(_cell(row, columns, f.CONTENT_TYPE), platform),
        text=text,
        media_url=media_url[:2048] if media_url else None,
        permalink=permalink[:2048] if permalink else None,
        published_at=published_at,
        **_content_metrics(row, columns),
    )


def _external_id(
    post_id: str, permalink: str | None, published_at: str, text: str | None
) -> str:
    """
    The platform's own post ID where the export has it, so the post merges
    with the one the sync stores; otherwise a stable ID derived from the
    post, so importing the same file twice updates rather than duplicates.
    """
    if post_id:
        # Spreadsheet tools turn long numeric IDs into 1.23E+17: unusable
        if not re.fullmatch(r"\d(\.\d+)?e\+\d+", post_id.lower()):
            return post_id[:255]
    if permalink:
        tweet = _TWEET_URL.search(permalink)
        if tweet:
            return tweet[1]
    key = permalink or f"{published_at}|{text or ''}"
    return "import-" + hashlib.sha256(key.encode()).hexdigest()[:32]


def _content_type(value: str, platform: Platform) -> ContentType:
    kind = value.lower()
    for keyword, content_type in (
        ("reel", ContentType.reel),
        ("story", ContentType.story),
        ("short", ContentType.short),
        ("article", ContentType.article),
        ("video", ContentType.video),
    ):
        if keyword in kind:
            return content_type
    if platform is Platform.tiktok:
        return ContentType.video
    if platform is Platform.twitter:
        return ContentType.tweet
    return ContentType.post
