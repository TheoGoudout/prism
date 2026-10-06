"""Add the mailing platforms and the email content type

Revision ID: 3f8b1c6d2e47
Revises: 56ccfad11eb7
Create Date: 2026-10-06 09:00:00.000000

"""
from alembic import op


# revision identifiers, used by Alembic.
revision = '3f8b1c6d2e47'
down_revision = '56ccfad11eb7'
branch_labels = None
depends_on = None


def upgrade():
    # ADD VALUE can't run inside a transaction block on older PostgreSQL
    with op.get_context().autocommit_block():
        for platform in ("mailchimp", "klaviyo", "brevo"):
            op.execute(f"ALTER TYPE platform ADD VALUE IF NOT EXISTS '{platform}'")
        op.execute("ALTER TYPE contenttype ADD VALUE IF NOT EXISTS 'email'")


def downgrade():
    # PostgreSQL can't drop an enum value: remove the rows using them, then
    # recreate the types without them
    op.execute("DELETE FROM post WHERE content_type = 'email'")
    op.execute(
        "DELETE FROM integration WHERE platform IN ('mailchimp', 'klaviyo', 'brevo')"
    )
    op.execute("ALTER TYPE contenttype RENAME TO contenttype_old")
    op.execute(
        "CREATE TYPE contenttype AS ENUM "
        "('post', 'reel', 'story', 'video', 'tweet', 'article', 'short')"
    )
    op.execute(
        "ALTER TABLE post ALTER COLUMN content_type TYPE contenttype "
        "USING content_type::text::contenttype"
    )
    op.execute("DROP TYPE contenttype_old")
    op.execute("ALTER TYPE platform RENAME TO platform_old")
    op.execute(
        "CREATE TYPE platform AS ENUM "
        "('facebook', 'instagram', 'twitter', 'linkedin', 'tiktok', 'google_analytics')"
    )
    for table in ("integration", "platformaccount"):
        op.execute(
            f"ALTER TABLE {table} ALTER COLUMN platform TYPE platform "
            "USING platform::text::platform"
        )
    op.execute("DROP TYPE platform_old")
