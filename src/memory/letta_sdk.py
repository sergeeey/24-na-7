"""
Letta SDK интеграция для памяти пользователя.
Reflexio 24/7 — November 2025 Integration Sprint
"""
from typing import Dict, Any, Optional, List
from pathlib import Path
import json
import os

from src.utils.logging import get_logger

logger = get_logger("memory.letta")


class LettaSDK:
    """Обёртка для Letta SDK (Python) с кэшированием для экономии токенов."""
    
    def __init__(self, api_key: Optional[str] = None, cache_enabled: bool = True):
        """
        Инициализация Letta SDK.
        
        Args:
            api_key: API ключ Letta (если None, берётся из окружения)
            cache_enabled: Включить кэширование для экономии токенов
        """
        self.api_key = api_key or os.getenv("LETTA_API_KEY")
        self.base_url = os.getenv("LETTA_API_URL", "https://api.letta.ai/v1")
        self.client = None
        self.cache_enabled = cache_enabled
        self._memory_cache: Dict[str, Any] = {}  # Кэш для памяти
        self._token_savings = 0  # Счётчик сэкономленных токенов
        
        if self.api_key:
            try:
                # Импортируем Letta SDK (если установлен)
                import letta
                self.client = letta.Client(api_key=self.api_key)
                logger.info("letta_sdk_initialized", cache_enabled=cache_enabled)
            except ImportError:
                logger.warning("letta_sdk_not_installed", fallback="local_storage")
                self.client = None
        else:
            logger.warning("letta_api_key_not_set", using_local_storage=True)
    
    def store_memory(self, key: str, value: Any, memory_type: str = "core") -> bool:
        """
        Сохраняет память с обновлением кэша.
        
        Args:
            key: Ключ памяти
            value: Значение
            memory_type: "core" или "session"
            
        Returns:
            True если успешно
        """
        # Обновляем кэш
        cache_key = f"{memory_type}:{key}"
        if self.cache_enabled:
            self._memory_cache[cache_key] = value
        
        if self.client:
            try:
                if memory_type == "core":
                    self.client.core_memory.set(key, value)
                else:
                    self.client.session_memory.set(key, value)
                return True
            except Exception as e:
                logger.error("letta_store_failed", error=str(e), fallback="local")
        
        # Fallback на локальное хранилище
        return self._store_local(key, value, memory_type)
    
    def get_token_savings(self) -> int:
        """Возвращает количество сэкономленных токенов через кэширование."""
        return self._token_savings
    
    def clear_cache(self):
        """Очищает кэш памяти."""
        self._memory_cache.clear()
        logger.info("memory_cache_cleared")
    
    def get_memory(self, key: str, memory_type: str = "core") -> Optional[Any]:
        """
        Получает память с кэшированием для экономии токенов.
        
        Args:
            key: Ключ памяти
            memory_type: "core" или "session"
            
        Returns:
            Значение или None
        """
        # Проверяем кэш
        cache_key = f"{memory_type}:{key}"
        if self.cache_enabled and cache_key in self._memory_cache:
            logger.debug("memory_cache_hit", key=key, type=memory_type)
            self._token_savings += 50  # Примерная экономия токенов
            return self._memory_cache[cache_key]
        
        # Получаем из Letta или локального хранилища
        value = None
        if self.client:
            try:
                if memory_type == "core":
                    value = self.client.core_memory.get(key)
                else:
                    value = self.client.session_memory.get(key)
            except Exception as e:
                logger.warning("letta_get_failed", error=str(e), fallback="local")
        
        if value is None:
            value = self._get_local(key, memory_type)
        
        # Сохраняем в кэш
        if value is not None and self.cache_enabled:
            self._memory_cache[cache_key] = value
            # Ограничиваем размер кэша (максимум 1000 записей)
            if len(self._memory_cache) > 1000:
                # Удаляем самые старые записи (FIFO)
                oldest_key = next(iter(self._memory_cache))
                del self._memory_cache[oldest_key]
        
        return value
    
    def _store_local(self, key: str, value: Any, memory_type: str) -> bool:
        """Локальное хранилище (fallback)."""
        try:
            memory_dir = Path(".cursor/memory")
            memory_dir.mkdir(parents=True, exist_ok=True)
            
            if memory_type == "core":
                file_path = memory_dir / "core_memory.json"
            else:
                session_dir = memory_dir / "session_memory"
                session_dir.mkdir(parents=True, exist_ok=True)
                file_path = session_dir / f"{key}.json"
            
            # Загружаем существующие данные
            if file_path.exists():
                data = json.loads(file_path.read_text(encoding="utf-8"))
            else:
                data = {}
            
            data[key] = value
            
            file_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
            logger.info("memory_stored_locally", key=key, type=memory_type)
            return True
            
        except Exception as e:
            logger.error("local_memory_store_failed", error=str(e))
            return False
    
    def _get_local(self, key: str, memory_type: str) -> Optional[Any]:
        """Получение из локального хранилища."""
        try:
            memory_dir = Path(".cursor/memory")
            
            if memory_type == "core":
                file_path = memory_dir / "core_memory.json"
            else:
                file_path = memory_dir / "session_memory" / f"{key}.json"
            
            if file_path.exists():
                data = json.loads(file_path.read_text(encoding="utf-8"))
                return data.get(key)
            
            return None
            
        except Exception as e:
            logger.error("local_memory_get_failed", error=str(e))
            return None


def get_letta_client() -> LettaSDK:
    """Фабричная функция для получения Letta клиента."""
    return LettaSDK()

