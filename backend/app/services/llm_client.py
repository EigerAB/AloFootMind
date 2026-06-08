"""Unified LLM client factory for DeepSeek (and extensible for other providers)."""
from __future__ import annotations

from langchain_openai import ChatOpenAI
from openai import AsyncOpenAI

from app.core.config import settings

_deepseek_async_client: AsyncOpenAI | None = None


def get_deepseek_client() -> AsyncOpenAI:
    """Return a cached AsyncOpenAI client for DeepSeek (async API calls)."""
    global _deepseek_async_client
    if _deepseek_async_client is None:
        _deepseek_async_client = AsyncOpenAI(
            api_key=settings.DEEPSEEK_API_KEY,
            base_url=settings.DEEPSEEK_BASE_URL,
        )
    return _deepseek_async_client


def get_deepseek_llm(
    temperature: float = 0.3,
    max_tokens: int = 2000,
    streaming: bool = False,
    request_timeout: int | None = None,
) -> ChatOpenAI:
    """Return a LangChain ChatOpenAI instance configured for DeepSeek."""
    kwargs: dict = {
        "model": settings.DEEPSEEK_MODEL,
        "api_key": settings.DEEPSEEK_API_KEY,
        "base_url": settings.DEEPSEEK_BASE_URL,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "streaming": streaming,
    }
    if request_timeout is not None:
        kwargs["request_timeout"] = request_timeout
    return ChatOpenAI(**kwargs)
