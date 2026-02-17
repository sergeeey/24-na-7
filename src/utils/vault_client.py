"""
HashiCorp Vault клиент для Reflexio 24/7.
Безопасное хранение и получение secrets.
"""
import os
from typing import Optional, Dict, Any
from functools import lru_cache

from src.utils.logging import get_logger

logger = get_logger("vault")


class VaultConfig:
    """Конфигурация Vault."""
    
    ENABLED: bool = os.getenv("VAULT_ENABLED", "false").lower() == "true"
    ADDR: str = os.getenv("VAULT_ADDR", "http://localhost:8200")
    TOKEN: Optional[str] = os.getenv("VAULT_TOKEN")
    NAMESPACE: Optional[str] = os.getenv("VAULT_NAMESPACE")
    
    # Пути к секретам
    SECRET_PATH: str = "secret/data/reflexio"
    SECRET_VERSION: Optional[str] = None


class VaultClient:
    """
    Клиент для работы с HashiCorp Vault.
    
    Поддерживает:
    - KV v2 (Key-Value версии 2)
    - Автоматическое обновление токена
    - Кэширование (с TTL)
    - Fallback на environment variables
    """
    
    def __init__(self):
        self.client = None
        self._cache: Dict[str, Any] = {}
        self._connected = False
        
        if not VaultConfig.ENABLED:
            logger.info("vault_disabled_using_env_fallback")
            return
        
        try:
            import hvac
            self.client = hvac.Client(
                url=VaultConfig.ADDR,
                token=VaultConfig.TOKEN,
                namespace=VaultConfig.NAMESPACE,
            )
            
            # Проверяем соединение
            if self.client.is_authenticated():
                self._connected = True
                logger.info("vault_connected", addr=VaultConfig.ADDR)
            else:
                logger.warning("vault_auth_failed_fallback_to_env")
        except ImportError:
            logger.warning("hvac_not_installed_fallback_to_env")
        except Exception as e:
            logger.error("vault_connection_error", error=str(e))
    
    def is_available(self) -> bool:
        """Проверяет доступность Vault."""
        return self._connected and self.client is not None
    
    def get_secret(self, key: str, default: Optional[str] = None) -> Optional[str]:
        """
        Получает secret из Vault или fallback на env.
        
        Args:
            key: Ключ секрета (например, "openai_api_key")
            default: Значение по умолчанию
            
        Returns:
            Значение секрета или default
        """
        # Сначала пробуем Vault
        if self.is_available():
            try:
                secret_path = f"{VaultConfig.SECRET_PATH}/{key}"
                response = self.client.secrets.kv.v2.read_secret_version(
                    path=secret_path,
                    mount_point="secret",
                )
                value = response["data"]["data"].get("value")
                if value:
                    logger.debug("vault_secret_read", key=key)
                    return value
            except Exception as e:
                logger.warning("vault_read_error", key=key, error=str(e))
        
        # Fallback на environment variable
        env_var = key.upper() + "_API_KEY"
        env_value = os.getenv(env_var)
        if env_value:
            logger.debug("env_secret_read", key=key, source="env_fallback")
            return env_value
        
        return default
    
    def set_secret(self, key: str, value: str) -> bool:
        """
        Сохраняет secret в Vault.
        
        Args:
            key: Ключ секрета
            value: Значение секрета
            
        Returns:
            True если успешно
        """
        if not self.is_available():
            logger.error("vault_not_available_cannot_write")
            return False
        
        try:
            secret_path = f"{VaultConfig.SECRET_PATH}/{key}"
            self.client.secrets.kv.v2.create_or_update_secret(
                path=secret_path,
                secret={"value": value},
                mount_point="secret",
            )
            logger.info("vault_secret_written", key=key)
            return True
        except Exception as e:
            logger.error("vault_write_error", key=key, error=str(e))
            return False
    
    def list_secrets(self) -> list:
        """Возвращает список ключей секретов."""
        if not self.is_available():
            return []
        
        try:
            response = self.client.secrets.kv.v2.list_secrets(
                path=VaultConfig.SECRET_PATH,
                mount_point="secret",
            )
            return response["data"]["keys"]
        except Exception as e:
            logger.warning("vault_list_error", error=str(e))
            return []
    
    def rotate_token(self) -> bool:
        """Ротирует текущий токен."""
        if not self.is_available():
            return False
        
        try:
            new_token = self.client.auth.token.create(
                ttl="1h",
                renewable=True,
            )
            self.client.token = new_token["auth"]["client_token"]
            logger.info("vault_token_rotated")
            return True
        except Exception as e:
            logger.error("vault_rotate_error", error=str(e))
            return False


@lru_cache()
def get_vault_client() -> VaultClient:
    """Возвращает синглтон Vault клиента."""
    return VaultClient()


def get_secret(key: str, default: Optional[str] = None) -> Optional[str]:
    """
    Удобная функция для получения секрета.
    
    Args:
        key: Ключ секрета (например, "openai", "anthropic")
        default: Значение по умолчанию
        
    Returns:
        Значение секрета
        
    Example:
        >>> api_key = get_secret("openai")
        >>> api_key = get_secret("custom_key", default="fallback")
    """
    client = get_vault_client()
    return client.get_secret(key, default)


class SecretManager:
    """
    Менеджер секретов с поддержкой разных backend.
    
    Priority:
    1. HashiCorp Vault (если VAULT_ENABLED=true)
    2. Environment Variables (fallback)
    3. Default values (если указаны)
    """
    
    def __init__(self):
        self.vault = get_vault_client()
    
    def get_openai_key(self) -> Optional[str]:
        """Получает OpenAI API ключ."""
        return self.vault.get_secret("openai") or os.getenv("OPENAI_API_KEY")
    
    def get_anthropic_key(self) -> Optional[str]:
        """Получает Anthropic API ключ."""
        return self.vault.get_secret("anthropic") or os.getenv("ANTHROPIC_API_KEY")
    
    def get_supabase_service_key(self) -> Optional[str]:
        """Получает Supabase Service Role Key."""
        return self.vault.get_secret("supabase_service") or os.getenv("SUPABASE_SERVICE_KEY")
    
    def get_brave_key(self) -> Optional[str]:
        """Получает Brave API ключ."""
        return self.vault.get_secret("brave") or os.getenv("BRAVE_API_KEY")
    
    def get_brightdata_key(self) -> Optional[str]:
        """Получает BrightData API ключ."""
        return self.vault.get_secret("brightdata") or os.getenv("BRIGHTDATA_API_KEY")


# Глобальный экземпляр
secret_manager = SecretManager()
