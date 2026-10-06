"""The tools Prism migrates from through their API."""

from app.migrate.sources.base import ProfileData, Source, SourceAuthError
from app.migrate.sources.metricool import Metricool
from app.migrate.sources.sprout_social import SproutSocial
from app.models.migration import MigrationSource

SOURCES: dict[MigrationSource, Source] = {
    MigrationSource.sprout_social: SproutSocial(),
    MigrationSource.metricool: Metricool(),
}

__all__ = ["SOURCES", "ProfileData", "Source", "SourceAuthError"]
