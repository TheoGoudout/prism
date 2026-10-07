"""Make integrations and platform accounts unique

Reconnecting an account and syncing it update the existing rows; these
constraints guarantee it even under concurrent requests. Duplicates that may
already exist are merged first, keeping all of their history.

Revision ID: d7113a31148e
Revises: 3f8b1c6d2e47
Create Date: 2026-10-07 09:00:00.000000

"""
from alembic import op


# revision identifiers, used by Alembic.
revision = 'd7113a31148e'
down_revision = '3f8b1c6d2e47'
branch_labels = None
depends_on = None


def upgrade():
    # Duplicate integrations of one account: keep the one most likely to
    # hold working tokens, and move the others' accounts onto it
    op.execute("""
        CREATE TEMP TABLE duplicate_integration ON COMMIT DROP AS
        SELECT id, keep_id FROM (
            SELECT id, first_value(id) OVER (
                PARTITION BY workspace_id, platform, external_account_id
                ORDER BY status = 'active' DESC, last_synced_at DESC NULLS LAST,
                         created_at DESC NULLS LAST, id
            ) AS keep_id
            FROM integration
        ) ranked
        WHERE id <> keep_id
    """)
    op.execute("""
        UPDATE platformaccount SET integration_id = d.keep_id
        FROM duplicate_integration d WHERE platformaccount.integration_id = d.id
    """)
    op.execute("DELETE FROM integration USING duplicate_integration d WHERE integration.id = d.id")

    # Duplicate accounts of one integration: keep the oldest, move the others'
    # posts and days onto it (unless it has them too), then delete them
    op.execute("""
        CREATE TEMP TABLE duplicate_account ON COMMIT DROP AS
        SELECT id, keep_id FROM (
            SELECT id, first_value(id) OVER (
                PARTITION BY integration_id, external_id
                ORDER BY created_at NULLS LAST, id
            ) AS keep_id
            FROM platformaccount
        ) ranked
        WHERE id <> keep_id
    """)
    op.execute("""
        UPDATE post SET platform_account_id = d.keep_id
        FROM duplicate_account d
        WHERE post.platform_account_id = d.id
          AND NOT EXISTS (
              SELECT 1 FROM post kept
              WHERE kept.platform_account_id = d.keep_id
                AND kept.external_id = post.external_id
          )
    """)
    op.execute("""
        UPDATE metricsnapshot SET platform_account_id = d.keep_id
        FROM duplicate_account d
        WHERE metricsnapshot.platform_account_id = d.id
          AND NOT EXISTS (
              SELECT 1 FROM metricsnapshot kept
              WHERE kept.platform_account_id = d.keep_id
                AND kept.date = metricsnapshot.date
          )
    """)
    # Cascades to the posts and days the kept account already had
    op.execute("DELETE FROM platformaccount USING duplicate_account d WHERE platformaccount.id = d.id")

    op.create_unique_constraint(
        'uq_integration_workspace_platform_account',
        'integration',
        ['workspace_id', 'platform', 'external_account_id'],
    )
    op.create_unique_constraint(
        'uq_platformaccount_integration_external_id',
        'platformaccount',
        ['integration_id', 'external_id'],
    )


def downgrade():
    op.drop_constraint(
        'uq_platformaccount_integration_external_id', 'platformaccount', type_='unique'
    )
    op.drop_constraint(
        'uq_integration_workspace_platform_account', 'integration', type_='unique'
    )
