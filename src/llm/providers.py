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
        self.api_key = os.getenv("OPENAI_API_KEY")
        
        if not self.api_key:
            logger.warning("OPENAI_API_KEY not set")
            return
        
        try:
            import openai
            self.client = openai.OpenAI(api_key=self.api_key)
        except ImportError:
            logger.error("openai library not installed. Run: pip install openai")
    
    def call(self, prompt: str, system_prompt: Optional[str] = None, max_tokens: int = 1000, **kwargs) -> Dict[str, Any]:
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
            
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=self.temperature,
                max_tokens=max_tokens,
                **kwargs
            )
            
            latency_ms = (time.time() - start_time) * 1000
            response_text = response.choices[0].message.content
            
            # Логирование reasoning-трассировки (ответ)
            reasoning_trace.update({
                "response_length": len(response_text),
                "tokens_used": response.usage.total_tokens if response.usage else 0,
                "latency_ms": round(latency_ms, 2),
                "status": "success",
            })
            
            logger.info(
                "llm_call_completed",
                **reasoning_trace,
                response_preview=response_text[:200] if response_text else ""
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
        self.api_key = os.getenv("ANTHROPIC_API_KEY")
        
        if not self.api_key:
            logger.warning("ANTHROPIC_API_KEY not set")
            return
        
        try:
            import anthropic
            self.client = anthropic.Anthropic(api_key=self.api_key)
        except ImportError:
            logger.error("anthropic library not installed. Run: pip install anthropic")
    
    def call(self, prompt: str, system_prompt: Optional[str] = None, max_tokens: int = 1000, **kwargs) -> Dict[str, Any]:
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
            response = self.client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                temperature=self.temperature,
                system=system_prompt or "",
                messages=[{"role": "user", "content": prompt}],
                **kwargs
            )
            
            latency_ms = (time.time() - start_time) * 1000
            
            text = response.content[0].text if response.content else ""
            
            # Логирование reasoning-трассировки (ответ)
            reasoning_trace.update({
                "response_length": len(text),
                "tokens_used": response.usage.input_tokens + response.usage.output_tokens if response.usage else 0,
                "latency_ms": round(latency_ms, 2),
                "status": "success",
            })
            
            logger.info(
                "llm_call_completed",
                **reasoning_trace,
                response_preview=text[:200] if text else ""
            )
            
            return {
                "text": text,
                "tokens_used": response.usage.input_tokens + response.usage.output_tokens if response.usage else 0,
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
        self.api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
        
        if not self.api_key:
            logger.warning("GOOGLE_API_KEY not set")
            return
        
        try:
            import google.generativeai as genai
            genai.configure(api_key=self.api_key)
            self.client = genai.GenerativeModel(model)
        except ImportError:
            logger.error("google-generativeai library not installed. Run: pip install google-generativeai")
    
    def call(self, prompt: str, system_prompt: Optional[str] = None, max_tokens: int = 1000, **kwargs) -> Dict[str, Any]:
        """Вызывает Google Gemini API."""
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
            
            response = self.client.generate_content(
                full_prompt,
                generation_config={
                    "temperature": self.temperature,
                    "max_output_tokens": max_tokens,
                },
                **kwargs
            )
            
            latency_ms = (time.time() - start_time) * 1000
            
            text = response.text if hasattr(response, "text") else ""
            
            return {
                "text": text,
                "tokens_used": response.usage_metadata.total_token_count if hasattr(response, "usage_metadata") else 0,
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


def get_llm_client(role: str = "actor") -> Optional[LLMClient]:
    """
    Фабричная функция для получения LLM клиента.
    
    Args:
        role: "actor" или "critic"
        
    Returns:
        LLMClient или None
    """
    provider_name = os.getenv("LLM_PROVIDER", "openai").lower()
    model_key = f"LLM_MODEL_{role.upper()}"
    
    # ПОЧЕМУ: исправлены галлюцинированные имена моделей на актуальные (2026-02)
    default_models = {
        "openai": "gpt-4o-mini" if role == "actor" else "gpt-4o",
        "anthropic": "claude-haiku-4-5-20251001" if role == "actor" else "claude-sonnet-4-6",
        "google": "gemini-2.0-flash" if role == "actor" else "gemini-2.0-flash",
    }
    
    model = os.getenv(
        model_key,
        os.getenv("LLM_MODEL_ACTOR", default_models.get(provider_name, "gpt-4o-mini"))
    )
    
    temp_key = f"LLM_TEMPERATURE_{role.upper()}"
    temperature = float(os.getenv(temp_key, "0.3" if role == "actor" else "0.0"))
    
    try:
        if provider_name == "openai":
            return OpenAIClient(model=model, temperature=temperature)
        elif provider_name == "anthropic":
            return AnthropicClient(model=model, temperature=temperature)
        elif provider_name == "google":
            return GoogleGeminiClient(model=model, temperature=temperature)
        else:
            logger.warning("unknown_llm_provider", provider=provider_name)
            return None
    except Exception as e:
        logger.error("failed_to_create_llm_client", error=str(e))
        return None







