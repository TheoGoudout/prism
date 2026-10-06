import secrets
import warnings
from typing import Annotated, Any, Literal, Self

from pydantic import (
    AnyUrl,
    BeforeValidator,
    EmailStr,
    HttpUrl,
    PostgresDsn,
    computed_field,
    model_validator,
)
from pydantic_settings import BaseSettings, SettingsConfigDict


def parse_cors(v: Any) -> list[str] | str:
    if isinstance(v, str) and not v.startswith("["):
        return [i.strip() for i in v.split(",") if i.strip()]
    elif isinstance(v, list | str):
        return v
    raise ValueError(v)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        # Use top level .env file (one level above ./backend/)
        env_file="../.env",
        env_ignore_empty=True,
        extra="ignore",
    )
    API_V1_STR: str = "/api/v1"
    SECRET_KEY: str = secrets.token_urlsafe(32)
    # 60 minutes * 24 hours * 8 days = 8 days
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 8
    FRONTEND_HOST: str = "http://localhost:5173"
    ENVIRONMENT: Literal["local", "dev", "staging", "production"] = "local"

    BACKEND_CORS_ORIGINS: Annotated[
        list[AnyUrl] | str, BeforeValidator(parse_cors)
    ] = []

    @computed_field  # type: ignore[prop-decorator]
    @property
    def all_cors_origins(self) -> list[str]:
        return [str(origin).rstrip("/") for origin in self.BACKEND_CORS_ORIGINS] + [
            self.FRONTEND_HOST
        ]

    PROJECT_NAME: str
    SENTRY_DSN: HttpUrl | None = None
    POSTGRES_SERVER: str
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str
    POSTGRES_PASSWORD: str = ""
    POSTGRES_DB: str = ""

    @computed_field  # type: ignore[prop-decorator]
    @property
    def SQLALCHEMY_DATABASE_URI(self) -> PostgresDsn:
        return PostgresDsn.build(
            scheme="postgresql+psycopg",
            username=self.POSTGRES_USER,
            password=self.POSTGRES_PASSWORD,
            host=self.POSTGRES_SERVER,
            port=self.POSTGRES_PORT,
            path=self.POSTGRES_DB,
        )

    SMTP_TLS: bool = True
    SMTP_SSL: bool = False
    SMTP_PORT: int = 587
    SMTP_HOST: str | None = None
    SMTP_USER: str | None = None
    SMTP_PASSWORD: str | None = None
    EMAILS_FROM_EMAIL: EmailStr | None = None
    EMAILS_FROM_NAME: str | None = None

    @model_validator(mode="after")
    def _set_default_emails_from(self) -> Self:
        if not self.EMAILS_FROM_NAME:
            self.EMAILS_FROM_NAME = self.PROJECT_NAME
        return self

    EMAIL_RESET_TOKEN_EXPIRE_HOURS: int = 48

    @computed_field  # type: ignore[prop-decorator]
    @property
    def emails_enabled(self) -> bool:
        return bool(self.SMTP_HOST and self.EMAILS_FROM_EMAIL)

    EMAIL_TEST_USER: EmailStr = "test@example.com"
    FIRST_SUPERUSER: EmailStr
    FIRST_SUPERUSER_PASSWORD: str

    # OAuth2 credentials — optional; only required when the corresponding
    # platform integration is actually used.
    FACEBOOK_APP_ID: str = ""
    FACEBOOK_APP_SECRET: str = ""
    INSTAGRAM_APP_ID: str = ""
    INSTAGRAM_APP_SECRET: str = ""
    TWITTER_CLIENT_ID: str = ""
    TWITTER_CLIENT_SECRET: str = ""
    LINKEDIN_CLIENT_ID: str = ""
    LINKEDIN_CLIENT_SECRET: str = ""
    TIKTOK_CLIENT_KEY: str = ""
    TIKTOK_CLIENT_SECRET: str = ""
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""
    MAILCHIMP_CLIENT_ID: str = ""
    MAILCHIMP_CLIENT_SECRET: str = ""
    KLAVIYO_CLIENT_ID: str = ""
    KLAVIYO_CLIENT_SECRET: str = ""

    # Base URL used to construct OAuth2 redirect URIs
    API_BASE_URL: str = "http://localhost:8000"

    # Redis — used as Celery broker and result backend
    REDIS_URL: str = "redis://localhost:6379/0"

    # Follow-up syncs. On top of the nightly sync, an integration is synced
    # again soon after one of its posts is published or gains engagement,
    # less and less often while its posts stay quiet. See
    # app.services.sync_schedule.
    # A post has a new interaction when its engagements grow by this share
    # since the last one, so the bar scales with the account's audience...
    SYNC_MIN_ENGAGEMENT_GROWTH: float = 0.1
    # ...but never below this many engagements, so a lone like doesn't count
    SYNC_MIN_NEW_ENGAGEMENTS: int = 3
    # Stop the follow-up syncs after this long without any interaction
    SYNC_QUIET_DAYS: int = 2
    # Only posts published this recently are followed
    SYNC_FOLLOW_POST_DAYS: int = 7
    # Bounds of the time between two follow-up syncs
    SYNC_MIN_INTERVAL_MINUTES: int = 30
    SYNC_MAX_INTERVAL_HOURS: int = 12

    # AI / LangChain — set AI_PROVIDER to the desired backend
    # LangSmith tracing is enabled by setting LANGCHAIN_TRACING_V2=true and
    # LANGCHAIN_API_KEY in the environment (LangChain reads these automatically).
    AI_PROVIDER: Literal["openai", "anthropic", "google"] = "openai"
    AI_MODEL: str = "gpt-4o-mini"
    OPENAI_API_KEY: str = ""
    ANTHROPIC_API_KEY: str = ""
    GOOGLE_API_KEY: str = ""

    def _check_default_secret(self, var_name: str, value: str | None) -> None:
        if value == "changethis":
            message = (
                f'The value of {var_name} is "changethis", '
                "for security, please change it, at least for deployments."
            )
            if self.ENVIRONMENT == "local":
                warnings.warn(message, stacklevel=1)
            else:
                raise ValueError(message)

    @model_validator(mode="after")
    def _enforce_non_default_secrets(self) -> Self:
        # The random default differs per process (the API runs four workers)
        # and per restart, and the OAuth tokens stored in the database are
        # encrypted with a key derived from it — so outside local development
        # a missing SECRET_KEY must stop the app rather than fall back to it.
        if self.ENVIRONMENT != "local" and "SECRET_KEY" not in self.model_fields_set:
            raise ValueError(
                "SECRET_KEY must be set outside local development: it signs "
                "sessions and encrypts the stored OAuth tokens."
            )
        self._check_default_secret("SECRET_KEY", self.SECRET_KEY)
        self._check_default_secret("POSTGRES_PASSWORD", self.POSTGRES_PASSWORD)
        self._check_default_secret(
            "FIRST_SUPERUSER_PASSWORD", self.FIRST_SUPERUSER_PASSWORD
        )

        return self


settings = Settings()  # type: ignore
