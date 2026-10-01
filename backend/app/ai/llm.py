"""
LLM factory — returns a LangChain BaseChatModel configured from settings.

Switching providers is a one-line change in .env (AI_PROVIDER / AI_MODEL).
LangSmith tracing is enabled automatically when LANGCHAIN_TRACING_V2=true and
LANGCHAIN_API_KEY are set in the environment; no code changes needed.
"""

from langchain_core.language_models import BaseChatModel

from app.core.config import settings


def get_llm() -> BaseChatModel:
    """Return a configured chat model based on AI_PROVIDER setting."""
    provider = settings.AI_PROVIDER

    if provider == "anthropic":
        from langchain_anthropic import ChatAnthropic

        return ChatAnthropic(  # type: ignore[call-arg]
            model=settings.AI_MODEL,
            api_key=settings.ANTHROPIC_API_KEY or None,  # type: ignore[arg-type]
        )

    if provider == "google":
        from langchain_google_genai import ChatGoogleGenerativeAI

        return ChatGoogleGenerativeAI(
            model=settings.AI_MODEL,
            google_api_key=settings.GOOGLE_API_KEY or None,
        )

    # Default: OpenAI
    from langchain_openai import ChatOpenAI

    return ChatOpenAI(
        model=settings.AI_MODEL,
        api_key=settings.OPENAI_API_KEY or None,  # type: ignore[arg-type]
    )
