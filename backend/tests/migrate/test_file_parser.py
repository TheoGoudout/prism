from datetime import UTC, date, datetime

import pytest

from app.migrate.files.parser import ParsedFile, parse_export
from app.migrate.files.reading import ImportFileError
from app.models.integration import Platform
from app.models.metrics import ContentType
from app.models.migration import DataKind, ExportFormat


def _parse(
    text: str, platform: Platform, export_format: ExportFormat | None = None
) -> ParsedFile:
    return parse_export(text.encode(), platform=platform, export_format=export_format)


HOOTSUITE_POSTS = """\
Post performance,,,,,,,,,,,
"Mar 1, 2024 - Mar 31, 2024",,,,,,,,,,,
Date (GMT),Post ID,Post Message,Post Permalink,Post Type,Social Network,Impressions,Reach,Engagement,Likes,Comments,Shares,Post Link Clicks,Video Views
2024-03-01 14:30,111_222,Spring launch,https://facebook.com/111/posts/222,Photo,Facebook,"1,200",900,85,60,15,10,30,
2024-03-02 09:00,333,Behind the scenes,https://instagram.com/p/abc,Reel,Instagram,5000,4000,300,250,40,10,,4800
"""


def test_hootsuite_posts() -> None:
    parsed = _parse(HOOTSUITE_POSTS, Platform.facebook)
    assert parsed.export_format is ExportFormat.hootsuite
    assert parsed.kind is DataKind.posts
    assert parsed.rows_read == 2
    assert parsed.skipped_other_networks == 1
    assert parsed.rejected == 0
    [post] = parsed.posts
    assert post.external_id == "111_222"
    assert post.text == "Spring launch"
    assert post.permalink == "https://facebook.com/111/posts/222"
    assert post.published_at == datetime(2024, 3, 1, 14, 30, tzinfo=UTC)
    assert post.content_type is ContentType.post
    assert post.impressions == 1200
    assert post.reach == 900
    # Prism's engagements: likes + comments + shares, not the tool's figure
    assert post.engagements == 85
    assert post.clicks == 30
    assert post.views is None


SPROUT_POSTS = """\
Date,Post ID,Network,Post Type,Content Type,Profile,Sent by,Link,Post,Impressions,Reach,Engagements,Engagement Rate (per Impression),Reactions,Comments,Shares,Saves,Post Link Clicks,Video Views
03/15/2024 10:05 am,17890000000000001,Instagram,Post,Reel,Acme,Jane,https://www.instagram.com/reel/xyz,New collection,2000,1500,130,6.5%,100,20,5,5,,1800
"""


def test_sprout_social_posts() -> None:
    parsed = _parse(SPROUT_POSTS, Platform.instagram)
    assert parsed.export_format is ExportFormat.sprout_social
    [post] = parsed.posts
    assert post.external_id == "17890000000000001"
    assert post.text == "New collection"
    assert post.content_type is ContentType.reel
    assert post.published_at == datetime(2024, 3, 15, 10, 5, tzinfo=UTC)
    assert post.likes == 100
    assert post.saves == 5
    assert post.engagements == 130
    assert post.views == 1800


SPROUT_PROFILE = """\
Date,Profile,Network,Audience,Net Audience Growth,Audience Gained,Audience Lost,Impressions,Engagements,Post Link Clicks,Published Posts
03/01/2024,Acme,LinkedIn,"10,000",12,15,3,"4,500",210,40,2
03/02/2024,Acme,LinkedIn,"10,012",5,6,1,"3,900",180,22,1
"""


def test_sprout_social_profile_metrics() -> None:
    parsed = _parse(SPROUT_PROFILE, Platform.linkedin)
    assert parsed.export_format is ExportFormat.sprout_social
    assert parsed.kind is DataKind.daily_metrics
    first, second = parsed.snapshots
    assert first.date == date(2024, 3, 1)
    assert first.followers_count == 10_000
    assert first.followers_gained == 15
    assert first.followers_lost == 3
    assert first.impressions == 4500
    # No likes or comments: the tool's figure is kept
    assert first.engagements == 210
    assert first.clicks == 40
    assert first.posts_count == 2
    assert second.followers_count == 10_012


BUFFER_POSTS = """\
Date,Update,Service,Service Link,Type,Impressions,Reach,Engagements,Likes,Comments,Shares,Clicks
2024-04-02T08:00:00Z,Read our new blog post,twitter,https://x.com/acme/status/1775000000000000000,text,800,,25,15,4,6,12
"""


def test_buffer_posts() -> None:
    parsed = _parse(BUFFER_POSTS, Platform.twitter)
    assert parsed.export_format is ExportFormat.buffer
    [post] = parsed.posts
    # The tweet ID is read from the link, so the post merges with the synced one
    assert post.external_id == "1775000000000000000"
    assert post.content_type is ContentType.tweet
    assert post.engagements == 25


METRICOOL_ACCOUNT = """\
Date;Followers;Gained followers;Lost followers;Posts;Impressions;Reach;Interactions
01/04/2024;2.345;12;-3;1;1.200;900;45
13/04/2024;2.360;20;-5;0;800;600;30
"""


def test_metricool_daily_metrics() -> None:
    parsed = _parse(METRICOOL_ACCOUNT, Platform.instagram)
    assert parsed.export_format is ExportFormat.metricool
    assert parsed.kind is DataKind.daily_metrics
    first, second = parsed.snapshots
    assert first.date == date(2024, 4, 1)  # day first
    assert second.date == date(2024, 4, 13)
    assert first.followers_count == 2345
    assert first.followers_lost == 3
    assert first.impressions == 1200
    assert first.engagements == 45


LATER_POSTS = """\
Posted At,Caption,Media Type,Post URL,Impressions,Reach,Likes,Comments,Saves,Shares,Video Views
"Apr 5, 2024 6:15 PM",Our new cafe,Video,https://www.tiktok.com/@acme/video/7350000000000000000,3000,2500,200,12,8,4,2900
"""


def test_later_posts() -> None:
    parsed = _parse(LATER_POSTS, Platform.tiktok)
    assert parsed.export_format is ExportFormat.later
    [post] = parsed.posts
    assert post.text == "Our new cafe"
    assert post.content_type is ContentType.video
    assert post.published_at == datetime(2024, 4, 5, 18, 15, tzinfo=UTC)
    assert post.engagements == 224
    assert post.external_id.startswith("import-")


AGORAPULSE_POSTS = """\
Publishing date,Publishing time,Message,Link,Impressions,Reach,Reactions,Comments,Shares,Clicks
05/04/2024,17:45,Bonjour !,https://facebook.com/1/posts/2,500,400,30,5,2,8
"""


def test_agorapulse_posts() -> None:
    parsed = _parse(AGORAPULSE_POSTS, Platform.facebook)
    assert parsed.export_format is ExportFormat.agorapulse
    [post] = parsed.posts
    assert post.published_at == datetime(2024, 4, 5, 17, 45, tzinfo=UTC)
    assert post.likes == 30
    assert post.engagements == 37


def test_explicit_source_overrides_detection() -> None:
    parsed = _parse(AGORAPULSE_POSTS, Platform.facebook, ExportFormat.hootsuite)
    assert parsed.export_format is ExportFormat.hootsuite
    # Hootsuite reads numeric dates month first
    assert parsed.posts[0].published_at.month == 5


def test_generic_csv_and_stable_ids() -> None:
    text = "date,text,likes,comments\n2024-01-01,Hello,3,1\n2024-01-01,Hello,3,1\n"
    parsed = _parse(text, Platform.linkedin)
    assert parsed.export_format is ExportFormat.csv
    first, second = parsed.posts
    assert first.external_id == second.external_id


def test_bad_rows_are_reported_and_summary_rows_ignored() -> None:
    text = (
        "Date,Impressions,Likes\n"
        "2024-01-01,100,5\n"
        "not a date,100,5\n"
        "2024-01-03,lots,5\n"
        "Total,200,10\n"
    )
    parsed = _parse(text, Platform.facebook)
    assert parsed.rows_read == 3
    assert len(parsed.snapshots) == 1
    assert parsed.rejected == 2
    assert parsed.errors == [
        "Line 3: 'not a date' is not a date",
        "Line 4: impressions: 'lots' is not a number",
    ]


def test_scientific_notation_ids_fall_back_to_the_link() -> None:
    text = (
        "Date,Post ID,Link,Likes\n"
        "2024-01-01,1.78E+17,https://instagram.com/p/a,3\n"
        "2024-01-01,1.78E+17,https://instagram.com/p/b,3\n"
    )
    first, second = _parse(text, Platform.instagram).posts
    assert first.external_id != second.external_id


def test_several_profiles_are_refused() -> None:
    text = "Date,Profile,Network,Impressions\n2024-01-01,A,Facebook,1\n2024-01-01,B,Facebook,2\n"
    with pytest.raises(ImportFileError, match="several profiles"):
        _parse(text, Platform.facebook)


def test_unrecognised_file_is_refused() -> None:
    with pytest.raises(ImportFileError, match="No header row"):
        _parse("name,email\nJane,jane@example.com\n", Platform.facebook)
