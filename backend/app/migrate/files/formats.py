"""
How each tool names its export columns.

Every column is matched on its normalised header (lowercase, punctuation
collapsed to spaces), so "Date (GMT)" and "date gmt" are the same column. A
tool's own aliases are tried before the common ones, which cover the names
most tools share ("Impressions", "Likes", …).
"""

import re
from dataclasses import dataclass, field

from app.models.migration import ExportFormat

# Canonical fields a column can map onto
DATE = "date"
# A separate time-of-day column, when the date column has none
TIME = "time"
POST_ID = "post_id"
TEXT = "text"
PERMALINK = "permalink"
MEDIA_URL = "media_url"
CONTENT_TYPE = "content_type"
NETWORK = "network"
PROFILE = "profile"

IMPRESSIONS = "impressions"
REACH = "reach"
VIEWS = "views"
ENGAGEMENTS = "engagements"
LIKES = "likes"
COMMENTS = "comments"
SHARES = "shares"
CLICKS = "clicks"
SAVES = "saves"

FOLLOWERS_COUNT = "followers_count"
FOLLOWERS_GAINED = "followers_gained"
FOLLOWERS_LOST = "followers_lost"
POSTS_COUNT = "posts_count"

CONTENT_METRICS = (
    IMPRESSIONS,
    REACH,
    VIEWS,
    ENGAGEMENTS,
    LIKES,
    COMMENTS,
    SHARES,
    CLICKS,
    SAVES,
)
ACCOUNT_METRICS = (FOLLOWERS_COUNT, FOLLOWERS_GAINED, FOLLOWERS_LOST, POSTS_COUNT)
# A column that only a per-post export has
POST_FIELDS = (POST_ID, TEXT, PERMALINK)


def normalise_header(header: str) -> str:
    """ "Engagement Rate (per Impression)" → "engagement rate per impression"."""
    return re.sub(r"[^0-9a-z]+", " ", header.lower()).strip()


COMMON_ALIASES: dict[str, tuple[str, ...]] = {
    DATE: (
        "date",
        "date gmt",
        "date utc",
        "day",
        "published",
        "published at",
        "published date",
        "published time",
        "publish date",
        "publishing date",
        "post date",
        "posted at",
        "posted on",
        "sent at",
        "created at",
        "created time",
    ),
    TIME: ("time", "post time", "publishing time", "hour"),
    POST_ID: ("post id", "id", "content id", "media id", "tweet id", "video id"),
    TEXT: (
        "text",
        "post text",
        "message",
        "post message",
        "caption",
        "content",
        "description",
        "title",
    ),
    PERMALINK: (
        "permalink",
        "post permalink",
        "link",
        "post link",
        "url",
        "post url",
        "link to post",
    ),
    MEDIA_URL: ("media url", "image url", "image", "thumbnail", "thumbnail url"),
    CONTENT_TYPE: ("content type", "post type", "media type", "type", "format"),
    NETWORK: ("network", "social network", "platform", "channel", "service"),
    PROFILE: ("profile", "account", "account name", "profile name", "page"),
    IMPRESSIONS: ("impressions", "total impressions", "post impressions"),
    REACH: ("reach", "total reach", "post reach", "accounts reached"),
    VIEWS: ("views", "video views", "plays", "video plays", "total plays"),
    ENGAGEMENTS: (
        "engagements",
        "engagement",
        "total engagements",
        "total engagement",
        "interactions",
    ),
    LIKES: ("likes", "reactions", "favorites", "favourites", "hearts"),
    COMMENTS: ("comments", "replies"),
    SHARES: ("shares", "retweets", "reposts", "reshares"),
    CLICKS: ("clicks", "link clicks", "post link clicks", "post clicks", "url clicks"),
    SAVES: ("saves", "saved", "bookmarks"),
    FOLLOWERS_COUNT: (
        "followers",
        "total followers",
        "followers count",
        "fans",
        "page fans",
        "audience",
        "total audience",
    ),
    FOLLOWERS_GAINED: (
        "followers gained",
        "new followers",
        "gained followers",
        "follows",
        "new fans",
    ),
    FOLLOWERS_LOST: (
        "followers lost",
        "lost followers",
        "unfollows",
        "unfollowers",
        "unlikes",
    ),
    POSTS_COUNT: ("published posts", "posts", "posts published", "number of posts"),
}


@dataclass(frozen=True)
class SourceFormat:
    label: str
    # Headers only this tool writes, used to detect it from a file
    signatures: tuple[str, ...] = ()
    # Its own names for a field, tried before the common ones
    aliases: dict[str, tuple[str, ...]] = field(default_factory=dict)
    # How to read an ambiguous numeric date like 03/04/2024
    day_first: bool = False

    def aliases_for(self, name: str) -> tuple[str, ...]:
        return self.aliases.get(name, ()) + COMMON_ALIASES.get(name, ())


FORMATS: dict[ExportFormat, SourceFormat] = {
    ExportFormat.hootsuite: SourceFormat(
        label="Hootsuite",
        signatures=("post permalink", "post message", "date gmt", "social network"),
        aliases={
            ENGAGEMENTS: ("engagement",),
            FOLLOWERS_COUNT: ("followers", "page followers"),
        },
    ),
    ExportFormat.sprout_social: SourceFormat(
        label="Sprout Social",
        signatures=(
            "sent by",
            "engagement rate per impression",
            "net audience growth",
            "audience gained",
        ),
        aliases={
            TEXT: ("post",),
            FOLLOWERS_COUNT: ("audience", "followers"),
            FOLLOWERS_GAINED: ("audience gained", "followers gained"),
            FOLLOWERS_LOST: ("audience lost", "followers lost"),
        },
    ),
    ExportFormat.buffer: SourceFormat(
        label="Buffer",
        signatures=("service link", "update", "sent at", "service"),
        aliases={TEXT: ("update", "post text", "text"), PERMALINK: ("service link",)},
    ),
    ExportFormat.metricool: SourceFormat(
        label="Metricool",
        signatures=("interactions", "gained followers", "lost followers", "saved"),
        aliases={ENGAGEMENTS: ("interactions",)},
        day_first=True,
    ),
    ExportFormat.later: SourceFormat(
        label="Later",
        signatures=("caption", "media type", "posted at"),
        aliases={TEXT: ("caption",)},
    ),
    ExportFormat.agorapulse: SourceFormat(
        label="Agorapulse",
        signatures=("publishing date", "publishing time"),
        day_first=True,
    ),
    ExportFormat.csv: SourceFormat(label="CSV file"),
}


def detect_format(headers: list[str]) -> ExportFormat:
    """The tool whose signature headers the file has the most of."""
    present = {normalise_header(h) for h in headers}
    best, best_score = ExportFormat.csv, 0
    for export_format, fmt in FORMATS.items():
        score = len(present.intersection(fmt.signatures))
        if score > best_score:
            best, best_score = export_format, score
    return best
