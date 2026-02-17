"""LLM Client Factory — создание LLM clients из config."""
import logging
from typing import Optional

from src.utils.config import settings
from src.llm.providers import LLMClient, LLMProvider, OpenAIClient, AnthropicClient

logger = logging.getLogger(__name__)


def create_llm_client(
    provider: Optional[str] = None,
    model: Optional[str] = None,
    temperature: float = 0.3,
) -> Optional[LLMClient]:
    """Создаёт LLM client из config.

    Args:
        provider: LLM provider (openai | anthropic), default: settings.LLM_PROVIDER
        model: Model name, default: settings.LLM_MODEL_ACTOR
        temperature: Temperature для generation

    Returns:
        LLMClient или None (если API key отсутствует)

    Example:
        >>> client = create_llm_client()
        >>> result = client.call("Summarize this text...")
    """
    provider = provider or settings.LLM_PROVIDER
    model = model or settings.LLM_MODEL_ACTOR

    if provider == LLMProvider.OPENAI.value:
        if not settings.OPENAI_API_KEY:
            logger.warning(
                "OPENAI_API_KEY not set, LLM client will be None (mock mode)"
            )
            return None

        logger.info(
            "llm_client_created",
            provider="openai",
            model=model,
            temperature=temperature,
        )
        return OpenAIClient(model=model, temperature=temperature)

    elif provider == LLMProvider.ANTHROPIC.value:
        if not settings.ANTHROPIC_API_KEY:
            logger.warning(
                "ANTHROPIC_API_KEY not set, LLM client will be None (mock mode)"
            )
            return None

        logger.info(
            "llm_client_created",
            provider="anthropic",
            model=model,
            temperature=temperature,
        )
        return AnthropicClient(model=model, temperature=temperature)

    else:
        logger.error(f"Unknown LLM provider: {provider}, falling back to None (mock)")
        return None


def create_cove_client() -> Optional[LLMClient]:
    """Создаёт LLM client для CoVe pipeline.

    Использует COVE-специфичные настройки:
    - Model: LLM_MODEL_CRITIC (более строгая модель)
    - Temperature: LLM_TEMPERATURE_CRITIC (0.0 для детерминизма)

    Returns:
        LLMClient или None (если ENABLE_COVE=false или нет API key)
    """
    if not settings.ENABLE_COVE:
        logger.info("CoVe disabled (ENABLE_COVE=false), returning None (mock mode)")
        return None

    return create_llm_client(
        provider=settings.LLM_PROVIDER,
        model=settings.LLM_MODEL_CRITIC,
        temperature=settings.LLM_TEMPERATURE_CRITIC,
    )


__all__ = ["create_llm_client", "create_cove_client"]
