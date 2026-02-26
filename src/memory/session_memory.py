"""
Session Memory — временные контексты встреч.
Reflexio 24/7 — November 2025 Integration Sprint
"""
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
import json

from src.memory.letta_sdk import get_letta_client
from src.utils.config import settings
from src.utils.logging import get_logger

logger = get_logger("memory.session")


class SessionMemory:
    """Управление session memory (временные контексты)."""

    def __init__(self):
        self.client = get_letta_client()
        self.session_dir = settings.STORAGE_PATH / "session_memory"
        self.legacy_session_dir = Path(".cursor/memory/session_memory")
        self._migrate_legacy_sessions_if_needed()
        self.session_dir.mkdir(parents=True, exist_ok=True)

    def _migrate_legacy_sessions_if_needed(self) -> None:
        """Одноразово переносит legacy session files в src/storage."""
        if self.session_dir.exists() or not self.legacy_session_dir.exists():
            return
        try:
            self.session_dir.mkdir(parents=True, exist_ok=True)
            for legacy_file in self.legacy_session_dir.glob("*.json"):
                target = self.session_dir / legacy_file.name
                if not target.exists():
                    target.write_text(legacy_file.read_text(encoding="utf-8"), encoding="utf-8")
            logger.info(
                "session_memory_legacy_migrated",
                source=str(self.legacy_session_dir),
                target=str(self.session_dir),
            )
        except Exception as e:
            logger.warning("session_memory_legacy_migration_failed", error=str(e))

    def create_session(self, session_id: str, metadata: Optional[Dict[str, Any]] = None) -> bool:
        """
        Создаёт новую сессию.

        Args:
            session_id: Уникальный ID сессии
            metadata: Метаданные сессии

        Returns:
            True если успешно
        """
        try:
            session_data = {
                "session_id": session_id,
                "created_at": datetime.now().isoformat(),
                "metadata": metadata or {},
                "contexts": [],
            }

            session_file = self.session_dir / f"{session_id}.json"
            session_file.write_text(
                json.dumps(session_data, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )

            # Сохраняем в Letta SDK
            self.client.store_memory(f"session_{session_id}", session_data, memory_type="session")

            logger.info("session_created", session_id=session_id)
            return True

        except Exception as e:
            logger.error("session_creation_failed", error=str(e))
            return False

    def add_context(self, session_id: str, context: Dict[str, Any]) -> bool:
        """
        Добавляет контекст в сессию.

        Args:
            session_id: ID сессии
            context: Контекст (текст, timestamp, metadata)

        Returns:
            True если успешно
        """
        try:
            session_file = self.session_dir / f"{session_id}.json"

            if session_file.exists():
                session_data = json.loads(session_file.read_text(encoding="utf-8"))
            else:
                self.create_session(session_id)
                session_data = json.loads(session_file.read_text(encoding="utf-8"))

            context["added_at"] = datetime.now().isoformat()
            session_data["contexts"].append(context)

            session_file.write_text(
                json.dumps(session_data, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )

            logger.info("context_added", session_id=session_id, context_count=len(session_data["contexts"]))
            return True

        except Exception as e:
            logger.error("context_add_failed", error=str(e))
            return False

    def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Получает данные сессии."""
        try:
            # Пробуем Letta SDK
            session_data = self.client.get_memory(f"session_{session_id}", memory_type="session")
            if session_data:
                return session_data

            # Fallback на локальный файл
            session_file = self.session_dir / f"{session_id}.json"
            if session_file.exists():
                return json.loads(session_file.read_text(encoding="utf-8"))

            return None

        except Exception as e:
            logger.error("session_get_failed", error=str(e))
            return None

    def list_sessions(self) -> List[str]:
        """Возвращает список всех сессий."""
        try:
            sessions = []
            for session_file in self.session_dir.glob("*.json"):
                sessions.append(session_file.stem)
            return sorted(sessions)
        except Exception as e:
            logger.error("session_list_failed", error=str(e))
            return []


def get_session_memory() -> SessionMemory:
    """Фабричная функция для получения SessionMemory."""
    return SessionMemory()
