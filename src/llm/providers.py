"""
LLM Providers — интеграция с OpenAI и Anthropic.
"""

import os
import time
from typing import Dict, Any, Optional
from enum import Enum

try:
    from src.utils.logging import setup_logging, get_logger

    setup_logging()
    logger = get_logger("llm.providers")
except Exception:
    import logging

    logger = logging.getLogger("llm.providers")

from src.utils.circuit_breaker import CircuitBreaker, CircuitBreakerError

# Глобальные circuit breakers для каждого провайдера
_openai_circuit_breaker = CircuitBreaker(
    failure_threshold=5,
    timeout=60,
    expected_exception=Exception,
    name="openai_llm",
)

_anthropic_circuit_breaker = CircuitBreaker(
    failure_threshold=5,
    timeout=60,
    expected_exception=Exception,
    name="anthropic_llm",
)

_google_circuit_breaker = CircuitBreaker(
    failure_threshold=5,
    timeout=60,
    expected_exception=Exception,
    name="google_llm",
)


def get_llm_circuit_breaker_stats() -> dict[str, dict[str, Any]]:
    """Return current breaker stats for all configured LLM providers."""
    return {
        "openai": _openai_circuit_breaker.get_stats(),
        "anthropic": _anthropic_circuit_breaker.get_stats(),
        "google": _google_circuit_breaker.get_stats(),
    }


class LLMProvider(str, Enum):
    """Доступные LLM провайдеры."""

    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GOOGLE = "google"  # Gemini


class LLMClient:
    """Базовый клиент для LLM."""

    def __init__(self, provider: LLMProvider, model: str, temperature: float = 0.3):
        self.provider = provider
        self.model = model
        self.temperature = temperature
        self.api_key = None
        self.client = None

    def call(self, prompt: str, system_prompt: Optional[str] = None, **kwargs) -> Dict[str, Any]:
        """
        Вызывает LLM с промптом.

        Returns:
            Ответ с text, tokens_used, latency_ms
        """
        raise NotImplementedError


class OpenAIClient(LLMClient):
    """Клиент для OpenAI API."""

    def __init__(self, model: str, temperature: float = 0.3):
        super().__init__(LLMProvider.OPENAI, model, temperature)
        # ПОЧЕМУ: pydantic-settings не экспортирует в os.environ
        try:
            from src.utils.config import settings as _s

            self.api_key = getattr(_s, "OPENAI_API_KEY", None) or os.getenv("OPENAI_API_KEY")
        except Exception:
            self.api_key = os.getenv("OPENAI_API_KEY")

        if not self.api_key:
            logger.warning("OPENAI_API_KEY not set")
            return

        try:
            import openai

            self.client = openai.OpenAI(api_key=self.api_key)
        except ImportError:
            logger.error("openai library not installed. Run: pip install openai")

    def call(
        self, prompt: str, system_prompt: Optional[str] = None, max_tokens: int = 1000, **kwargs
    ) -> Dict[str, Any]:
        """Вызывает OpenAI API через circuit breaker."""
        if not self.client:
            return {
                "text": "",
                "error": "OpenAI client not initialized",
                "tokens_used": 0,
                "latency_ms": 0,
            }

        def _call_openai() -> Dict[str, Any]:
            start_time = time.time()

            # Логирование reasoning-трассировки (без дублирования event — structlog использует первый аргумент как event)
            reasoning_trace = {
                "provider": "openai",
                "model": self.model,
                "prompt_length": len(prompt),
                "system_prompt_length": len(system_prompt) if system_prompt else 0,
                "temperature": self.temperature,
                "max_tokens": max_tokens,
                "timestamp": time.time(),
            }
            logger.info("llm_call_started", **reasoning_trace)

            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})
            try:
                from src.utils.config import settings as _cfg

                timeout = kwargs.pop("timeout", getattr(_cfg, "LLM_TIMEOUT_SEC", 120.0))
            except Exception:
                timeout = kwargs.pop("timeout", 120.0)
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=self.temperature,
                max_tokens=max_tokens,
                timeout=timeout,
                **kwargs,
            )

            latency_ms = (time.time() - start_time) * 1000
            response_text = response.choices[0].message.content

            # Логирование reasoning-трассировки (ответ)
            reasoning_trace.update(
                {
                    "response_length": len(response_text),
                    "tokens_used": response.usage.total_tokens if response.usage else 0,
                    "latency_ms": round(latency_ms, 2),
                    "status": "success",
                }
            )

            logger.info(
                "llm_call_completed",
                **reasoning_trace,
                response_preview=response_text[:200] if response_text else "",
            )

            return {
                "text": response_text,
                "tokens_used": response.usage.total_tokens if response.usage else 0,
                "latency_ms": round(latency_ms, 2),
                "model": self.model,
                "reasoning_trace": reasoning_trace,  # Добавляем reasoning trace в ответ
            }

        try:
            return _openai_circuit_breaker.call(_call_openai)
        except CircuitBreakerError as e:
            logger.error("circuit_breaker_open", provider="openai", error=str(e))
            return {
                "text": "",
                "error": f"Circuit breaker is OPEN: {str(e)}",
                "tokens_used": 0,
                "latency_ms": 0,
            }
        except Exception as e:
            logger.error("llm_call_failed", provider="openai", error=str(e))
            return {
                "text": "",
                "error": str(e),
                "tokens_used": 0,
                "latency_ms": 0,
            }


class AnthropicClient(LLMClient):
    """Клиент для Anthropic API."""

    def __init__(self, model: str, temperature: float = 0.3):
        super().__init__(LLMProvider.ANTHROPIC, model, temperature)
        try:
            from src.utils.config import settings as _s

            self.api_key = getattr(_s, "ANTHROPIC_API_KEY", None) or os.getenv("ANTHROPIC_API_KEY")
        except Exception:
            self.api_key = os.getenv("ANTHROPIC_API_KEY")

        if not self.api_key:
            logger.warning("ANTHROPIC_API_KEY not set")
            return

        try:
            import anthropic

            self.client = anthropic.Anthropic(api_key=self.api_key)
        except ImportError:
            logger.error("anthropic library not installed. Run: pip install anthropic")

    def call(
        self, prompt: str, system_prompt: Optional[str] = None, max_tokens: int = 1000, **kwargs
    ) -> Dict[str, Any]:
        """Вызывает Anthropic API."""
        if not self.client:
            return {
                "text": "",
                "error": "Anthropic client not initialized",
                "tokens_used": 0,
                "latency_ms": 0,
            }

        start_time = time.time()

        # Логирование reasoning-трассировки
        reasoning_trace = {
            "provider": "anthropic",
            "model": self.model,
            "prompt_length": len(prompt),
            "system_prompt_length": len(system_prompt) if system_prompt else 0,
            "temperature": self.temperature,
            "max_tokens": max_tokens,
            "timestamp": time.time(),
        }

        logger.info("llm_call_started", **reasoning_trace)

        try:
            try:
                from src.utils.config import settings as _cfg

                timeout = kwargs.pop("timeout", getattr(_cfg, "LLM_TIMEOUT_SEC", 120.0))
            except Exception:
                timeout = kwargs.pop("timeout", 120.0)
            response = self.client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                temperature=self.temperature,
                system=system_prompt or "",
                messages=[{"role": "user", "content": prompt}],
                timeout=timeout,
                **kwargs,
            )

            latency_ms = (time.time() - start_time) * 1000

            text = response.content[0].text if response.content else ""

            # Логирование reasoning-трассировки (ответ)
            reasoning_trace.update(
                {
                    "response_length": len(text),
                    "tokens_used": response.usage.input_tokens + response.usage.output_tokens
                    if response.usage
                    else 0,
                    "latency_ms": round(latency_ms, 2),
                    "status": "success",
                }
            )

            logger.info(
                "llm_call_completed", **reasoning_trace, response_preview=text[:200] if text else ""
            )

            return {
                "text": text,
                "tokens_used": response.usage.input_tokens + response.usage.output_tokens
                if response.usage
                else 0,
                "latency_ms": round(latency_ms, 2),
                "model": self.model,
                "reasoning_trace": reasoning_trace,
            }
        except Exception as e:
            latency_ms = (time.time() - start_time) * 1000
            error_msg = str(e)

            logger.error(
                "llm_call_failed",
                provider="anthropic",
                error=error_msg,
                latency_ms=round(latency_ms, 2),
            )

            return {
                "text": "",
                "error": error_msg,
                "tokens_used": 0,
                "latency_ms": round(latency_ms, 2),
            }


class GoogleGeminiClient(LLMClient):
    """Клиент для Google Gemini API."""

    def __init__(self, model: str, temperature: float = 0.3):
        super().__init__(LLMProvider.GOOGLE, model, temperature)
        try:
            from src.utils.config import settings as _s

            self.api_key = (
                getattr(_s, "GOOGLE_API_KEY", None)
                or getattr(_s, "GEMINI_API_KEY", None)
                or os.getenv("GOOGLE_API_KEY")
                or os.getenv("GEMINI_API_KEY")
            )
        except Exception:
            self.api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")

        if not self.api_key:
            logger.warning("GOOGLE_API_KEY not set")
            return

        try:
            # ПОЧЕМУ google.genai: старый google.generativeai задепрекейтен Google (2025).
            # Новый SDK: from google import genai → client = genai.Client(api_key=...).
            from google import genai

            self.client = genai.Client(api_key=self.api_key)
        except ImportError:
            logger.error("google-genai library not installed. Run: pip install google-genai")

    def call(
        self, prompt: str, system_prompt: Optional[str] = None, max_tokens: int = 1000, **kwargs
    ) -> Dict[str, Any]:
        """Вызывает Google Gemini API через новый google.genai SDK."""
        if not self.client:
            return {
                "text": "",
                "error": "Gemini client not initialized",
                "tokens_used": 0,
                "latency_ms": 0,
            }

        start_time = time.time()

        try:
            full_prompt = prompt
            if system_prompt:
                full_prompt = f"{system_prompt}\n\n{prompt}"

            # ПОЧЕМУ contents=full_prompt: новый SDK принимает строку напрямую,
            # generation_config через types.GenerateContentConfig.
            from google.genai import types

            response = self.client.models.generate_content(
                model=self.model,
                contents=full_prompt,
                config=types.GenerateContentConfig(
                    temperature=self.temperature,
                    max_output_tokens=max_tokens,
                    response_mime_type="application/json",
                ),
            )

            latency_ms = (time.time() - start_time) * 1000

            text = response.text if hasattr(response, "text") else ""
            tokens_used = 0
            if hasattr(response, "usage_metadata") and response.usage_metadata:
                tokens_used = getattr(response.usage_metadata, "total_token_count", 0) or 0

            return {
                "text": text,
                "tokens_used": tokens_used,
                "latency_ms": round(latency_ms, 2),
                "model": self.model,
            }
        except Exception as e:
            logger.error("gemini_call_failed", error=str(e))
            return {
                "text": "",
                "error": str(e),
                "tokens_used": 0,
                "latency_ms": round((time.time() - start_time) * 1000, 2),
            }


class CascadeLLMClient(LLMClient):
    """
    Каскадный клиент: перебирает провайдеров по порядку.

    ПОЧЕМУ каскад, а не retry: разные провайдеры падают по разным причинам
    (rate limit, outage, key expired). Каскад даёт resilience без ожидания.
    Gemini Flash бесплатен → ставим первым → $5/мес → $0 при нормальной работе.
    """

    def __init__(self, clients: list[LLMClient]):
        # ПОЧЕМУ первый клиент как "основной": для совместимости с кодом,
        # который читает client.provider / client.model
        first = clients[0] if clients else None
        super().__init__(
            provider=first.provider if first else LLMProvider.OPENAI,
            model=first.model if first else "cascade",
            temperature=first.temperature if first else 0.3,
        )
        self.clients = clients

    def call(self, prompt: str, system_prompt: Optional[str] = None, **kwargs) -> Dict[str, Any]:
        """Перебирает провайдеров: первый успешный ответ — победитель.

        validate_fn (kwargs): опциональная функция валидации ответа.
        Если validate_fn(text) выбрасывает исключение — провайдер считается
        неудачным и cascade пробует следующего. Это позволяет отсеивать
        невалидный JSON от Gemini без хардкода в cascade.
        """
        errors = []
        validate_fn = kwargs.pop("validate_fn", None)

        for client in self.clients:
            provider_name = client.provider.value
            try:
                result = client.call(prompt, system_prompt=system_prompt, **kwargs)

                # Пустой text или наличие error → fallback к следующему
                if result.get("error") or not result.get("text"):
                    err_msg = result.get("error", "empty response")
                    logger.warning(
                        "cascade_provider_skipped",
                        provider=provider_name,
                        reason=err_msg,
                    )
                    errors.append(f"{provider_name}: {err_msg}")
                    continue

                # ПОЧЕМУ validate_fn здесь: cascade не знает про JSON,
                # но вызывающий код может передать валидатор.
                # Невалидный ответ → пробуем следующего провайдера вместо
                # молчаливого возврата пустышки.
                if validate_fn:
                    try:
                        validate_fn(result["text"])
                    except Exception as ve:
                        logger.warning(
                            "cascade_provider_validation_failed",
                            provider=provider_name,
                            error=str(ve),
                        )
                        errors.append(f"{provider_name}: validation failed: {ve}")
                        continue

                # Успех — логируем кто ответил
                logger.info(
                    "cascade_provider_success",
                    provider=provider_name,
                    model=client.model,
                )
                result["cascade_provider"] = provider_name
                return result

            except Exception as e:
                logger.warning(
                    "cascade_provider_exception",
                    provider=provider_name,
                    error=str(e),
                )
                errors.append(f"{provider_name}: {str(e)}")
                continue

        # Все провайдеры упали
        all_errors = "; ".join(errors)
        logger.error("cascade_all_failed", errors=all_errors)
        return {
            "text": "",
            "error": f"All cascade providers failed: {all_errors}",
            "tokens_used": 0,
            "latency_ms": 0,
            "cascade_provider": "none",
        }


def get_llm_client(role: str = "actor") -> Optional[LLMClient]:
    """
    Фабричная функция для получения LLM клиента.

    Args:
        role: "actor" или "critic"

    Returns:
        LLMClient или None
    """
    # ПОЧЕМУ: pydantic-settings загружает .env в объект settings, но НЕ в os.environ.
    # os.getenv() не видит значения из .env → дефолтил на openai → пустое саммари.
    # Теперь читаем из settings (pydantic) с fallback на os.getenv.
    try:
        from src.utils.config import settings as _settings

        provider_name = getattr(_settings, "LLM_PROVIDER", None) or os.getenv(
            "LLM_PROVIDER", "openai"
        )
        provider_name = provider_name.lower()

        model_attr = f"LLM_MODEL_{role.upper()}"
        model_env_key = f"LLM_MODEL_{role.upper()}"

        default_models = {
            "openai": "gpt-4o-mini" if role == "actor" else "gpt-4o",
            "anthropic": "claude-haiku-4-5-20251001" if role == "actor" else "claude-sonnet-4-6",
            "google": "gemini-2.5-flash" if role == "actor" else "gemini-2.5-flash",
        }

        model = (
            getattr(_settings, model_attr, None)
            or os.getenv(model_env_key)
            or getattr(_settings, "LLM_MODEL_ACTOR", None)
            or os.getenv("LLM_MODEL_ACTOR")
            or default_models.get(provider_name, "gpt-4o-mini")
        )

        temp_attr = f"LLM_TEMPERATURE_{role.upper()}"
        default_temp = 0.3 if role == "actor" else 0.0
        temperature = float(
            getattr(_settings, temp_attr, None) or os.getenv(temp_attr, str(default_temp))
        )
    except Exception:
        # Fallback если settings недоступны
        provider_name = os.getenv("LLM_PROVIDER", "openai").lower()
        default_models = {
            "openai": "gpt-4o-mini" if role == "actor" else "gpt-4o",
            "anthropic": "claude-haiku-4-5-20251001" if role == "actor" else "claude-sonnet-4-6",
            "google": "gemini-2.5-flash" if role == "actor" else "gemini-2.5-flash",
        }
        model = os.getenv(
            f"LLM_MODEL_{role.upper()}", default_models.get(provider_name, "gpt-4o-mini")
        )
        temperature = float(
            os.getenv(f"LLM_TEMPERATURE_{role.upper()}", "0.3" if role == "actor" else "0.0")
        )

    try:
        if provider_name == "openai":
            return OpenAIClient(model=model, temperature=temperature)
        elif provider_name == "anthropic":
            return AnthropicClient(model=model, temperature=temperature)
        elif provider_name == "google":
            return GoogleGeminiClient(model=model, temperature=temperature)
        elif provider_name == "cascade":
            # ПОЧЕМУ cascade отдельной веткой: обратная совместимость —
            # LLM_PROVIDER=anthropic продолжает работать как раньше
            cascade_order_str = ""
            try:
                from src.utils.config import settings as _cascade_settings

                cascade_order_str = getattr(_cascade_settings, "LLM_CASCADE_ORDER", "") or ""
            except Exception:
                pass
            cascade_order_str = cascade_order_str or os.getenv(
                "LLM_CASCADE_ORDER", "google,anthropic,openai"
            )

            cascade_defaults = {
                "google": ("gemini-2.5-flash", GoogleGeminiClient),
                "anthropic": ("claude-haiku-4-5-20251001", AnthropicClient),
                "openai": ("gpt-4o-mini", OpenAIClient),
            }

            clients: list[LLMClient] = []
            for name in cascade_order_str.split(","):
                name = name.strip().lower()
                if name in cascade_defaults:
                    default_model, client_cls = cascade_defaults[name]
                    clients.append(client_cls(model=default_model, temperature=temperature))

            if not clients:
                logger.warning("cascade_no_valid_providers", order=cascade_order_str)
                return None

            return CascadeLLMClient(clients=clients)
        else:
            logger.warning("unknown_llm_provider", provider=provider_name)
            return None
    except Exception as e:
        logger.error("failed_to_create_llm_client", error=str(e))
        return None
