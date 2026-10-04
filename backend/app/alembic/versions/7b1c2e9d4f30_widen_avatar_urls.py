"""Widen avatar URLs to 2048 characters

Instagram's CDN avatar URLs carry long signed query strings that overflow
512 characters.

Revision ID: 7b1c2e9d4f30
Revises: 2d37fe2875d0
Create Date: 2026-10-04 21:00:00.000000

"""
from alembic import op
import sqlmodel.sql.sqltypes


# revision identifiers, used by Alembic.
revision = '7b1c2e9d4f30'
down_revision = '2d37fe2875d0'
branch_labels = None
depends_on = None

_COLUMNS = [
    ('integration', 'external_account_avatar'),
    ('platformaccount', 'avatar_url'),
]


def upgrade():
    for table, column in _COLUMNS:
        op.alter_column(
            table,
            column,
            type_=sqlmodel.sql.sqltypes.AutoString(length=2048),
            existing_type=sqlmodel.sql.sqltypes.AutoString(length=512),
            existing_nullable=True,
        )


def downgrade():
    for table, column in _COLUMNS:
        # A longer URL can't be kept anyway, and a cut one is broken: drop it
        op.execute(
            f"UPDATE {table} SET {column} = NULL WHERE length({column}) > 512"
        )
        op.alter_column(
            table,
            column,
            type_=sqlmodel.sql.sqltypes.AutoString(length=512),
            existing_type=sqlmodel.sql.sqltypes.AutoString(length=2048),
            existing_nullable=True,
        )
