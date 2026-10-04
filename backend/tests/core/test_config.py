import pytest
from pydantic import ValidationError

from app.core.config import Settings

REQUIRED = {
    "PROJECT_NAME": "Prism",
    "POSTGRES_SERVER": "db",
    "POSTGRES_USER": "postgres",
    "POSTGRES_PASSWORD": "a-real-password",
    "FIRST_SUPERUSER": "admin@example.com",
    "FIRST_SUPERUSER_PASSWORD": "a-real-password",
}


def _settings(**overrides: str) -> Settings:
    # _env_file=None: only what the test passes, not the developer's .env
    return Settings(_env_file=None, **{**REQUIRED, **overrides})  # type: ignore[call-arg]


@pytest.mark.parametrize("environment", ["dev", "staging", "production"])
def test_missing_secret_key_is_refused_outside_local(
    monkeypatch: pytest.MonkeyPatch, environment: str
) -> None:
    monkeypatch.delenv("SECRET_KEY", raising=False)
    with pytest.raises(ValidationError, match="SECRET_KEY must be set"):
        _settings(ENVIRONMENT=environment)


def test_missing_secret_key_is_allowed_locally(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("SECRET_KEY", raising=False)
    assert _settings(ENVIRONMENT="local").SECRET_KEY


def test_explicit_secret_key_is_accepted_in_production() -> None:
    settings = _settings(ENVIRONMENT="production", SECRET_KEY="s3cret-value")
    assert settings.SECRET_KEY == "s3cret-value"
