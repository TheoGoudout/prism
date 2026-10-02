"""normalise engagement metrics across platforms

Brings rows stored by earlier syncs in line with the cross-platform
definitions, since a sync never erases a stored value with None:

- engagements = likes + comments + shares + saves on every platform:
  LinkedIn no longer counts clicks; Twitter/X counts quotes as shares and
  bookmarks as saves; Facebook Pages take engagements from their posts, so
  the daily page_post_engagements (which counts clicks) is cleared.
- engagement_rate = engagements / views (or impressions), instead of
  engagements / reach.

Revision ID: c4e2a9d7f1b3
Revises: 7b3cfafd351e
Create Date: 2026-10-02 09:00:00.000000

"""
from alembic import op

# revision identifiers, used by Alembic.
revision = 'c4e2a9d7f1b3'
down_revision = '7b3cfafd351e'
branch_labels = None
depends_on = None


def _accounts(platform: str) -> str:
    return f"SELECT id FROM platformaccount WHERE platform = '{platform}'"


def upgrade():
    op.execute(
        f"""
        UPDATE metricsnapshot SET engagements = NULL
        WHERE platform_account_id IN ({_accounts('facebook')})
        """
    )
    op.execute(
        f"""
        UPDATE post SET engagements = engagements - clicks
        WHERE platform_account_id IN ({_accounts('linkedin')})
          AND engagements IS NOT NULL AND clicks IS NOT NULL
        """
    )
    op.execute(
        f"""
        UPDATE post SET
            shares = COALESCE((raw_data->>'retweet_count')::int, 0)
                   + COALESCE((raw_data->>'quote_count')::int, 0),
            saves = (raw_data->>'bookmark_count')::int
        WHERE platform_account_id IN ({_accounts('twitter')})
          AND raw_data->>'retweet_count' IS NOT NULL
        """
    )
    op.execute(
        f"""
        UPDATE post SET engagements = COALESCE(likes, 0) + COALESCE(comments, 0)
                                    + COALESCE(shares, 0) + COALESCE(saves, 0)
        WHERE platform_account_id IN ({_accounts('twitter')})
          AND engagements IS NOT NULL
        """
    )
    for table in ("post", "metricsnapshot"):
        op.execute(
            f"""
            UPDATE {table} SET engagement_rate = ROUND(
                engagements::numeric / NULLIF(COALESCE(views, impressions), 0), 6
            )
            """
        )


def downgrade():
    # The previous values can't be recovered; the next syncs restore the old
    # definitions for the last 30 days if the code is rolled back too.
    pass
