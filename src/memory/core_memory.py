"""
Core Memory — предпочтения пользователя.
Reflexio 24/7 — November 2025 Integration Sprint
"""
from pathlib import Path
from typing import Any, Dict
import json

from src.memory.letta_sdk import get_letta_client
from src.utils.config import settings
from src.utils.logging import get_logger

logger = get_logger("memory.core")


class CoreMemory:
    """Управление core memory (предпочтения пользователя)."""

    def __init__(self):
        self.client = get_letta_client()
        self.memory_file = settings.STORAGE_PATH / "core_memory.json"
        self.legacy_memory_file = Path(".cursor/memory/core_memory.json")
        self._cache: Dict[str, Any] = {}
        self._migrate_legacy_cache_if_needed()
        self._load_cache()

    def _migrate_legacy_cache_if_needed(self) -> None:
        """Одноразово переносит legacy cache из .cursor в src/storage."""
        if self.memory_file.exists() or not self.legacy_memory_file.exists():
            return
        try:
            self.memory_file.parent.mkdir(parents=True, exist_ok=True)
            self.memory_file.write_text(
                self.legacy_memory_file.read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            logger.info(
                "core_memory_legacy_migrated",
                source=str(self.legacy_memory_file),
                target=str(self.memory_file),
            )
        except Exception as e:
            logger.warning("core_memory_legacy_migration_failed", error=str(e))

    def _load_cache(self):
        """Загружает cache из файла."""
        try:
            if self.memory_file.exists():
                self._cache = json.loads(self.memory_file.read_text(encoding="utf-8"))
                return
            if self.legacy_memory_file.exists():
                self._cache = json.loads(self.legacy_memory_file.read_text(encoding="utf-8"))
                return
            self._cache = {}
        except Exception as e:
            logger.warning("core_memory_load_failed", error=str(e))
            self._cache = {}

    def _save_cache(self):
        """Сохраняет cache в файл."""
        try:
            self.memory_file.parent.mkdir(parents=True, exist_ok=True)
            self.memory_file.write_text(
                json.dumps(self._cache, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception as e:
            logger.error("core_memory_save_failed", error=str(e))

    def get(self, key: str, default: Any = None) -> Any:
        """Получает значение из core memory."""
        # Пробуем Letta SDK
        value = self.client.get_memory(key, memory_type="core")
        if value is not None:
            return value

        # Fallback на локальный cache
        return self._cache.get(key, default)

    def set(self, key: str, value: Any) -> bool:
        """Устанавливает значение в core memory."""
        # Сохраняем в Letta SDK
        success = self.client.store_memory(key, value, memory_type="core")

        # Обновляем локальный cache
        self._cache[key] = value
        self._save_cache()

        return success

    def get_preferences(self) -> Dict[str, Any]:
        """Получает все предпочтения пользователя."""
        return {
            "language": self.get("preferred_language", "ru"),
            "timezone": self.get("timezone", "UTC"),
            "notification_time": self.get("notification_time", "23:00"),
            "digest_format": self.get("digest_format", "markdown"),
            "auto_transcribe": self.get("auto_transcribe", True),
            "opt_out_training": self.get("opt_out_training", False),
        }

    def set_preferences(self, preferences: Dict[str, Any]) -> bool:
        """Устанавливает предпочтения пользователя."""
        success = True
        for key, value in preferences.items():
            if not self.set(key, value):
                success = False
        return success

    def self_update_from_loop(self, loop_result: Dict[str, Any]) -> bool:
        """
        Обновляет core memory на основе результатов Reflexio-loop.

        Args:
            loop_result: Результат обработки через ReflexioLoop

        Returns:
            True если успешно
        """
        try:
            # Извлекаем инсайты из loop_result
            insights = []

            # Добавляем ключевые факты
            if loop_result.get("key_facts"):
                insights.extend(loop_result["key_facts"])

            # Добавляем эмоциональные паттерны
            if loop_result.get("emotions"):
                emotions = loop_result["emotions"]
                if emotions.get("primary_emotion"):
                    self.set("last_primary_emotion", emotions["primary_emotion"])
                if emotions.get("sentiment"):
                    self.set("last_sentiment", emotions["sentiment"])

            # Сохраняем инсайты
            existing_insights = self.get("insights", [])
            existing_insights.extend(insights)
            # Ограничиваем количество (последние 100)
            existing_insights = existing_insights[-100:]
            self.set("insights", existing_insights)

            # Обновляем метрики качества
            if loop_result.get("confidence_score"):
                confidence_history = self.get("confidence_history", [])
                confidence_history.append(
                    {
                        "score": loop_result["confidence_score"],
                        "timestamp": loop_result.get("processed_at"),
                    }
                )
                confidence_history = confidence_history[-50:]  # Последние 50
                self.set("confidence_history", confidence_history)

            logger.info("core_memory_updated_from_loop", insights_count=len(insights))
            return True

        except Exception as e:
            logger.error("core_memory_update_failed", error=str(e))
            return False


def get_core_memory() -> CoreMemory:
    """Фабричная функция для получения CoreMemory."""
    return CoreMemory()
