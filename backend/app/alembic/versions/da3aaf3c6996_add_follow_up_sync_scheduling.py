"""Add follow-up sync scheduling

Integrations are synced again, on top of the nightly sync, while their recent
posts are getting engagement. Existing posts start with no recorded
interaction: their publication stands in until the next sync.

Revision ID: da3aaf3c6996
Revises: 7b1c2e9d4f30
Create Date: 2026-10-05 20:32:54.545875

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'da3aaf3c6996'
down_revision = '7b1c2e9d4f30'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('integration', sa.Column('next_sync_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('post', sa.Column('last_engaged_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('post', sa.Column('engagements_at_last_engaged', sa.Integer(), nullable=True))


def downgrade():
    op.drop_column('post', 'engagements_at_last_engaged')
    op.drop_column('post', 'last_engaged_at')
    op.drop_column('integration', 'next_sync_at')
