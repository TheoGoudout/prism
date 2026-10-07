import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import jwt
from emails.message import Message
from jinja2 import Environment
from jwt.exceptions import InvalidTokenError

from app.core import security
from app.core.config import settings
from app.models.analysis import AnalysisResult

logger = logging.getLogger(__name__)


@dataclass
class EmailData:
    html_content: str
    subject: str


def render_email_template(*, template_name: str, context: dict[str, Any]) -> str:
    template_str = (
        Path(__file__).parent / "email-templates" / "build" / template_name
    ).read_text()
    # Escaped: contexts can hold text we don't control (e.g. AI output)
    return Environment(autoescape=True).from_string(template_str).render(context)


def _email(subject: str, template_name: str, **context: Any) -> EmailData:
    """An email of the project, from one of the templates."""
    html_content = render_email_template(
        template_name=template_name,
        context={"project_name": settings.PROJECT_NAME, **context},
    )
    return EmailData(
        html_content=html_content, subject=f"{settings.PROJECT_NAME} - {subject}"
    )


def send_email(*, email_to: str, email: EmailData) -> None:
    from_email = settings.EMAILS_FROM_EMAIL
    assert settings.emails_enabled and from_email, (
        "no provided configuration for email variables"
    )
    message = Message(
        subject=email.subject,
        html=email.html_content,
        mail_from=(settings.EMAILS_FROM_NAME, from_email),
    )
    smtp_options = {"host": settings.SMTP_HOST, "port": settings.SMTP_PORT}
    if settings.SMTP_TLS:
        smtp_options["tls"] = True
    elif settings.SMTP_SSL:
        smtp_options["ssl"] = True
    if settings.SMTP_USER:
        smtp_options["user"] = settings.SMTP_USER
    if settings.SMTP_PASSWORD:
        smtp_options["password"] = settings.SMTP_PASSWORD
    response = message.send(to=email_to, smtp=smtp_options)
    logger.info(f"send email result: {response}")


def generate_reset_password_email(email_to: str, email: str, token: str) -> EmailData:
    return _email(
        f"Password recovery for user {email}",
        "reset_password.html",
        username=email,
        email=email_to,
        valid_hours=settings.EMAIL_RESET_TOKEN_EXPIRE_HOURS,
        link=f"{settings.FRONTEND_HOST}/reset-password?token={token}",
    )


def generate_new_account_email(
    email_to: str, username: str, password: str
) -> EmailData:
    return _email(
        f"New account for user {username}",
        "new_account.html",
        username=username,
        password=password,
        email=email_to,
        link=settings.FRONTEND_HOST,
    )


def generate_analysis_email(
    *,
    workspace_name: str,
    analysis_id: uuid.UUID,
    date_from: date,
    date_to: date,
    result: AnalysisResult,
    yearly: bool = False,
) -> EmailData:
    title = "AI year in review" if yearly else "AI performance analysis"
    return _email(
        f"{workspace_name} {title.removeprefix('AI ')} ({date_from} to {date_to})",
        "performance_analysis.html",
        workspace_name=workspace_name,
        date_from=date_from.isoformat(),
        date_to=date_to.isoformat(),
        summary=result.summary,
        what_worked=result.what_worked,
        what_didnt_work=result.what_didnt_work,
        recommendations=result.recommendations,
        topics=result.topics,
        periods=result.periods,
        title=title,
        link=f"{settings.FRONTEND_HOST}/ai-analysis?analysis={analysis_id}",
    )


def generate_password_reset_token(email: str) -> str:
    delta = timedelta(hours=settings.EMAIL_RESET_TOKEN_EXPIRE_HOURS)
    now = datetime.now(UTC)
    expires = now + delta
    exp = expires.timestamp()
    encoded_jwt = jwt.encode(
        {"exp": exp, "nbf": now, "sub": email},
        settings.SECRET_KEY,
        algorithm=security.ALGORITHM,
    )
    return encoded_jwt


def verify_password_reset_token(token: str) -> str | None:
    try:
        decoded_token = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[security.ALGORITHM]
        )
        return str(decoded_token["sub"])
    except InvalidTokenError:
        return None
