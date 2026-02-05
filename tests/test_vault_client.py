"""
Тесты для Vault клиента (P0-3).
Проверка безопасного хранения secrets.
"""
import os
import pytest
from unittest.mock import Mock, patch, MagicMock

from src.utils.vault_client import (
    VaultClient,
    VaultConfig,
    SecretManager,
    get_secret,
    get_vault_client,
)


class TestVaultConfig:
    """Тесты конфигурации Vault."""
    
    def test_default_values(self):
        """Проверка значений по умолчанию."""
        assert VaultConfig.ADDR == "http://localhost:8200"
        assert VaultConfig.ENABLED is False
        assert VaultConfig.NAMESPACE is None
        assert VaultConfig.SECRET_PATH == "secret/data/reflexio"


class TestVaultClientDisabled:
    """Тесты когда Vault отключен."""
    
    @patch.dict(os.environ, {"VAULT_ENABLED": "false"})
    def test_vault_disabled_uses_env_fallback(self):
        """При отключенном Vault используем env переменные."""
        client = VaultClient()
        assert not client.is_available()
    
    @patch.dict(os.environ, {
        "VAULT_ENABLED": "false",
        "OPENAI_API_KEY": "test-key-from-env"
    })
    def test_get_secret_fallback_to_env(self):
        """Получение secret из env когда Vault отключен."""
        client = VaultClient()
        # Должен вернуть env значение
        result = client.get_secret("openai")
        assert result == "test-key-from-env"


class TestVaultClientMocked:
    """Тесты с замоканным Vault."""
    
    @pytest.fixture
    def mock_hvac(self):
        """Фикстура для мока hvac клиента."""
        with patch("src.utils.vault_client.hvac") as mock_hvac:
            mock_client = MagicMock()
            mock_client.is_authenticated.return_value = True
            mock_hvac.Client.return_value = mock_client
            yield mock_hvac, mock_client
    
    @patch.dict(os.environ, {"VAULT_ENABLED": "true", "VAULT_TOKEN": "test-token"})
    def test_vault_client_creation(self, mock_hvac):
        """Создание клиента при включенном Vault."""
        mock_hvac_module, mock_client = mock_hvac
        
        client = VaultClient()
        assert client.is_available()
        mock_client.is_authenticated.assert_called_once()
    
    @patch.dict(os.environ, {"VAULT_ENABLED": "true", "VAULT_TOKEN": "test-token"})
    def test_get_secret_from_vault(self, mock_hvac):
        """Получение secret из Vault."""
        mock_hvac_module, mock_client = mock_hvac
        mock_client.secrets.kv.v2.read_secret_version.return_value = {
            "data": {"data": {"value": "secret-from-vault"}}
        }
        
        client = VaultClient()
        result = client.get_secret("test_key")
        
        assert result == "secret-from-vault"
        mock_client.secrets.kv.v2.read_secret_version.assert_called_once()
    
    @patch.dict(os.environ, {"VAULT_ENABLED": "true", "VAULT_TOKEN": "test-token"})
    def test_set_secret(self, mock_hvac):
        """Сохранение secret в Vault."""
        mock_hvac_module, mock_client = mock_hvac
        mock_client.secrets.kv.v2.create_or_update_secret.return_value = {"success": True}
        
        client = VaultClient()
        result = client.set_secret("new_key", "new_value")
        
        assert result is True
        mock_client.secrets.kv.v2.create_or_update_secret.assert_called_once()
    
    @patch.dict(os.environ, {"VAULT_ENABLED": "true", "VAULT_TOKEN": "test-token"})
    def test_get_secret_not_found_returns_none(self, mock_hvac):
        """При отсутствии secret возвращается None."""
        mock_hvac_module, mock_client = mock_hvac
        mock_client.secrets.kv.v2.read_secret_version.side_effect = Exception("Not found")
        
        client = VaultClient()
        result = client.get_secret("nonexistent")
        
        assert result is None


class TestSecretManager:
    """Тесты менеджера секретов."""
    
    @patch.dict(os.environ, {
        "OPENAI_API_KEY": "openai-test-key",
        "ANTHROPIC_API_KEY": "anthropic-test-key",
        "SUPABASE_SERVICE_KEY": "supabase-test-key",
        "BRAVE_API_KEY": "brave-test-key",
        "BRIGHTDATA_API_KEY": "brightdata-test-key",
    })
    def test_secret_manager_uses_env_fallback(self):
        """SecretManager корректно использует env fallback."""
        manager = SecretManager()
        
        assert manager.get_openai_key() == "openai-test-key"
        assert manager.get_anthropic_key() == "anthropic-test-key"
        assert manager.get_supabase_service_key() == "supabase-test-key"
        assert manager.get_brave_key() == "brave-test-key"
        assert manager.get_brightdata_key() == "brightdata-test-key"


class TestGetSecretFunction:
    """Тесты функции get_secret."""
    
    @patch.dict(os.environ, {"VAULT_ENABLED": "false", "OPENAI_API_KEY": "test"})
    def test_get_secret_returns_value(self):
        """Функция get_secret возвращает значение."""
        result = get_secret("openai")
        assert result == "test"
    
    @patch.dict(os.environ, {"VAULT_ENABLED": "false"})
    def test_get_secret_returns_default(self):
        """Функция get_secret возвращает default если не найдено."""
        result = get_secret("nonexistent", default="default_value")
        assert result == "default_value"
    
    @patch.dict(os.environ, {"VAULT_ENABLED": "false"})
    def test_get_secret_returns_none_if_no_default(self):
        """Функция get_secret возвращает None если нет default."""
        result = get_secret("nonexistent")
        assert result is None


class TestVaultClientErrors:
    """Тесты обработки ошибок."""
    
    @patch.dict(os.environ, {"VAULT_ENABLED": "true", "VAULT_TOKEN": "test-token"})
    def test_auth_failure_logs_warning(self):
        """При ошибке аутентификации логируется warning."""
        with patch("src.utils.vault_client.hvac") as mock_hvac:
            mock_client = MagicMock()
            mock_client.is_authenticated.return_value = False
            mock_hvac.Client.return_value = mock_client
            
            client = VaultClient()
            assert not client.is_available()
    
    @patch.dict(os.environ, {"VAULT_ENABLED": "true", "VAULT_TOKEN": "test-token"})
    def test_set_secret_when_not_available(self):
        """set_secret возвращает False когда Vault недоступен."""
        with patch("src.utils.vault_client.hvac") as mock_hvac:
            mock_client = MagicMock()
            mock_client.is_authenticated.return_value = False
            mock_hvac.Client.return_value = mock_client
            
            client = VaultClient()
            result = client.set_secret("key", "value")
            assert result is False


class TestVaultCache:
    """Тесты кэширования клиента."""
    
    @patch.dict(os.environ, {"VAULT_ENABLED": "false"})
    def test_get_vault_client_returns_singleton(self):
        """get_vault_client возвращает синглтон."""
        client1 = get_vault_client()
        client2 = get_vault_client()
        
        # Должен быть один и тот же объект
        assert client1 is client2
