"""Add kind and email recipients to performance analysis

Revision ID: 2d37fe2875d0
Revises: 5ce89f0c2b24
Create Date: 2026-10-02 08:04:30.746858

"""
from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes


# revision identifiers, used by Alembic.
revision = '2d37fe2875d0'
down_revision = '5ce89f0c2b24'
branch_labels = None
depends_on = None


def upgrade():
    analysis_kind = sa.Enum('standard', 'yearly', name='analysiskind')
    analysis_kind.create(op.get_bind(), checkfirst=True)
    # Server defaults fill the existing rows
    op.add_column('performanceanalysis', sa.Column('kind', analysis_kind, nullable=False, server_default='standard'))
    op.add_column('performanceanalysis', sa.Column('email_recipients', sa.JSON(), nullable=False, server_default='[]'))
    op.alter_column('performanceanalysis', 'kind', server_default=None)
    op.alter_column('performanceanalysis', 'email_recipients', server_default=None)


def downgrade():
    op.drop_column('performanceanalysis', 'email_recipients')
    op.drop_column('performanceanalysis', 'kind')
    sa.Enum(name='analysiskind').drop(op.get_bind(), checkfirst=True)
