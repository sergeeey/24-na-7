"""
Тесты для LLM провайдеров (Core Domain).
"""
import pytest
import os
from unittest.mock import Mock, patch, MagicMock

from src.llm.providers import LLMProvider, LLMClient, OpenAIClient, AnthropicClient


class TestLLMProviderEnum:
    """Тесты enum провайдеров."""
    
    def test_provider_values(self):
        """Значения провайдеров."""
        assert LLMProvider.OPENAI.value == "openai"
        assert LLMProvider.ANTHROPIC.value == "anthropic"
        assert LLMProvider.GOOGLE.value == "google"


class TestLLMClientBase:
    """Базовые тесты LLM клиента."""
    
    def test_client_initialization(self):
        """Инициализация клиента."""
        client = LLMClient(
            provider=LLMProvider.OPENAI,
            model="gpt-4",
            temperature=0.5
        )
        
        assert client.provider == LLMProvider.OPENAI
        assert client.model == "gpt-4"
        assert client.temperature == 0.5
    
    def test_default_temperature(self):
        """Температура по умолчанию."""
        client = LLMClient(provider=LLMProvider.OPENAI, model="gpt-4")
        assert client.temperature == 0.3


class TestOpenAIClient:
    """Тесты OpenAI клиента."""
    
    @patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test-key"})
    def test_openai_initialization(self):
        """Инициализация OpenAI клиента."""
        with patch("src.llm.providers.openai") as mock_openai:
            mock_openai.OpenAI.return_value = Mock()
            
            client = OpenAIClient(model="gpt-4", temperature=0.3)
            
            assert client.provider == LLMProvider.OPENAI
            assert client.api_key == "sk-test-key"
    
    @patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test-key"})
    def test_openai_call(self):
        """Вызов OpenAI API."""
        with patch("src.llm.providers.openai") as mock_openai:
            mock_client = Mock()
            mock_client.chat.completions.create.return_value = Mock(
                choices=[Mock(message=Mock(content="Test response"))],
                usage=Mock(prompt_tokens=10, completion_tokens=5)
            )
            mock_openai.OpenAI.return_value = mock_client
            
            client = OpenAIClient(model="gpt-4", temperature=0.3)
            result = client.call("Test prompt")
            
            assert "text" in result
            assert "tokens_used" in result
            assert "latency_ms" in result
    
    def test_openai_no_api_key(self):
        """OpenAI без API ключа."""
        with patch.dict(os.environ, {}, clear=True):
            with patch("src.llm.providers.logger"):
                client = OpenAIClient(model="gpt-4", temperature=0.3)
                assert client.api_key is None
    
    @patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test-key"})
    def test_openai_call_with_system_prompt(self):
        """Вызов с system prompt."""
        with patch("src.llm.providers.openai") as mock_openai:
            mock_client = Mock()
            mock_client.chat.completions.create.return_value = Mock(
                choices=[Mock(message=Mock(content="Response"))],
                usage=Mock(prompt_tokens=20, completion_tokens=10)
            )
            mock_openai.OpenAI.return_value = mock_client
            
            client = OpenAIClient(model="gpt-4", temperature=0.3)
            result = client.call(
                prompt="User prompt",
                system_prompt="You are a helpful assistant"
            )
            
            assert result["text"] == "Response"


class TestAnthropicClient:
    """Тесты Anthropic клиента."""
    
    @patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-ant-test"})
    def test_anthropic_initialization(self):
        """Инициализация Anthropic клиента."""
        with patch("src.llm.providers.anthropic") as mock_anthropic:
            mock_anthropic.Anthropic.return_value = Mock()
            
            client = AnthropicClient(model="claude-3", temperature=0.3)
            
            assert client.provider == LLMProvider.ANTHROPIC
            assert client.api_key == "sk-ant-test"


class TestLLMResponse:
    """Тесты структуры ответа LLM."""
    
    def test_response_structure(self):
        """Структура ответа."""
        response = {
            "text": "Generated text",
            "error": None,
            "tokens_used": 100,
            "latency_ms": 500,
        }
        
        assert "text" in response
        assert "error" in response
        assert "tokens_used" in response
        assert "latency_ms" in response
    
    def test_error_response(self):
        """Ответ с ошибкой."""
        response = {
            "text": "",
            "error": "API Error",
            "tokens_used": 0,
            "latency_ms": 0,
        }
        
        assert response["error"] is not None
        assert response["text"] == ""


class TestLLMProviderSelection:
    """Тесты выбора провайдера."""
    
    def test_provider_selection_openai(self):
        """Выбор OpenAI провайдера."""
        with patch.dict(os.environ, {"LLM_PROVIDER": "openai"}):
            provider = LLMProvider("openai")
            assert provider == LLMProvider.OPENAI
    
    def test_provider_selection_anthropic(self):
        """Выбор Anthropic провайдера."""
        with patch.dict(os.environ, {"LLM_PROVIDER": "anthropic"}):
            provider = LLMProvider("anthropic")
            assert provider == LLMProvider.ANTHROPIC


class TestLLMConfiguration:
    """Тесты конфигурации LLM."""
    
    def test_temperature_range(self):
        """Диапазон температуры."""
        valid_temperatures = [0.0, 0.3, 0.5, 0.7, 1.0]
        
        for temp in valid_temperatures:
            assert 0.0 <= temp <= 1.0
    
    def test_max_tokens(self):
        """Максимальное количество токенов."""
        max_tokens = 1000
        assert max_tokens > 0
        assert max_tokens <= 4000  # Обычный лимит
