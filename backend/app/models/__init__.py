"""
Database tables and API schemas, one module per domain.

Import names from the domain modules (e.g. ``app.models.user``). Importing
this package registers every table with ``SQLModel.metadata``, which Alembic
and cross-module relationships rely on.
"""

from app.models import (
    ai,
    analysis,
    common,
    integration,
    metrics,
    migration,
    user,
    workspace,
)

__all__ = [
    "ai",
    "analysis",
    "common",
    "integration",
    "metrics",
    "migration",
    "user",
    "workspace",
]
