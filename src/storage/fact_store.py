"""FactStore — Database CRUD для Fact Layer v4.

Класс для сохранения и извлечения фактов из БД.

Принципы:
    - Immutable: только INSERT, no UPDATE/DELETE
    - Versioning: факты помечены fact_version
    - Batch operations: INSERT multiple facts в одной транзакции

Использование:
    from src.storage.fact_store import FactStore

    store = FactStore(db_path="src/storage/reflexio.db")
    await store.store_facts(facts)
"""

import sqlite3
import json
from typing import List, Optional
from pathlib import Path
from datetime import datetime

from src.models.fact import Fact, SourceSpan


class FactStore:
    """Database store для фактов.

    Attributes:
        db_path: Путь к SQLite database
        conn: Database connection (если используется sync mode)
    """

    def __init__(self, db_path: str | Path = "src/storage/reflexio.db"):
        """Инициализация FactStore.

        Args:
            db_path: Путь к SQLite database
        """
        self.db_path = Path(db_path)

        if not self.db_path.exists():
            raise FileNotFoundError(f"Database not found: {self.db_path}")

    async def store_facts(self, facts: List[Fact]) -> int:
        """Сохранение фактов в БД (batch INSERT).

        Args:
            facts: Список фактов для сохранения

        Returns:
            Количество сохранённых фактов

        Raises:
            sqlite3.IntegrityError: Если факт с таким ID уже существует
        """
        if not facts:
            return 0

        # Sync implementation (для asyncio в будущем можно использовать aiosqlite)
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()

        try:
            # Batch INSERT
            for fact in facts:
                db_dict = fact.to_db_dict()

                cursor.execute(
                    """
                    INSERT INTO facts (
                        id, transcription_id, fact_text, timestamp, confidence,
                        created_at, extracted_by, fact_version, confidence_score,
                        extraction_method, source_span
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        db_dict["id"],
                        db_dict["transcription_id"],
                        db_dict["fact_text"],
                        db_dict["timestamp"],
                        db_dict["confidence"],
                        db_dict["created_at"],
                        db_dict["extracted_by"],
                        db_dict["fact_version"],
                        db_dict["confidence_score"],
                        db_dict["extraction_method"],
                        db_dict["source_span"],
                    ),
                )

            conn.commit()
            return len(facts)

        except Exception as e:
            conn.rollback()
            raise e

        finally:
            conn.close()

    def store_facts_sync(self, facts: List[Fact]) -> int:
        """Синхронная версия store_facts (для неasync контекстов).

        Args:
            facts: Список фактов для сохранения

        Returns:
            Количество сохранённых фактов
        """
        if not facts:
            return 0

        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()

        try:
            for fact in facts:
                db_dict = fact.to_db_dict()

                cursor.execute(
                    """
                    INSERT INTO facts (
                        id, transcription_id, fact_text, timestamp, confidence,
                        created_at, extracted_by, fact_version, confidence_score,
                        extraction_method, source_span
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        db_dict["id"],
                        db_dict["transcription_id"],
                        db_dict["fact_text"],
                        db_dict["timestamp"],
                        db_dict["confidence"],
                        db_dict["created_at"],
                        db_dict["extracted_by"],
                        db_dict["fact_version"],
                        db_dict["confidence_score"],
                        db_dict["extraction_method"],
                        db_dict["source_span"],
                    ),
                )

            conn.commit()
            return len(facts)

        except Exception as e:
            conn.rollback()
            raise e

        finally:
            conn.close()

    async def get_facts(
        self,
        transcription_id: str,
        version: str = "1.0",
        min_confidence: Optional[float] = None,
    ) -> List[Fact]:
        """Получение фактов по transcription_id.

        Args:
            transcription_id: ID транскрипции
            version: Версия фактов (default: "1.0" для v4)
            min_confidence: Минимальная уверенность (опционально)

        Returns:
            Список Fact объектов
        """
        # Sync implementation
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        try:
            query = """
                SELECT * FROM facts
                WHERE transcription_id = ? AND fact_version = ?
            """
            params = [transcription_id, version]

            if min_confidence is not None:
                query += " AND confidence_score >= ?"
                params.append(min_confidence)

            query += " ORDER BY timestamp ASC"

            cursor.execute(query, params)
            rows = cursor.fetchall()

            facts = []
            for row in rows:
                # Парсим source_span JSON
                source_span_json = json.loads(row["source_span"])
                source_span = SourceSpan(**source_span_json)

                # Создаём Fact объект
                fact = Fact(
                    fact_id=row["id"],
                    transcription_id=row["transcription_id"],
                    fact_text=row["fact_text"],
                    confidence_score=row["confidence_score"],
                    extraction_method=row["extraction_method"],
                    source_span=source_span,
                    fact_version=row["fact_version"],
                    timestamp=datetime.fromisoformat(str(row["timestamp"])),
                )
                facts.append(fact)

            return facts

        finally:
            conn.close()

    def get_facts_sync(
        self,
        transcription_id: str,
        version: str = "1.0",
        min_confidence: Optional[float] = None,
    ) -> List[Fact]:
        """Синхронная версия get_facts.

        Args:
            transcription_id: ID транскрипции
            version: Версия фактов
            min_confidence: Минимальная уверенность

        Returns:
            Список Fact объектов
        """
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        try:
            query = """
                SELECT * FROM facts
                WHERE transcription_id = ? AND fact_version = ?
            """
            params = [transcription_id, version]

            if min_confidence is not None:
                query += " AND confidence_score >= ?"
                params.append(min_confidence)

            query += " ORDER BY timestamp ASC"

            cursor.execute(query, params)
            rows = cursor.fetchall()

            facts = []
            for row in rows:
                source_span_json = json.loads(row["source_span"])
                source_span = SourceSpan(**source_span_json)

                fact = Fact(
                    fact_id=row["id"],
                    transcription_id=row["transcription_id"],
                    fact_text=row["fact_text"],
                    confidence_score=row["confidence_score"],
                    extraction_method=row["extraction_method"],
                    source_span=source_span,
                    fact_version=row["fact_version"],
                    timestamp=datetime.fromisoformat(str(row["timestamp"])),
                )
                facts.append(fact)

            return facts

        finally:
            conn.close()

    async def count_facts(
        self,
        transcription_id: Optional[str] = None,
        version: str = "1.0",
    ) -> int:
        """Подсчёт количества фактов.

        Args:
            transcription_id: ID транскрипции (если None — все факты)
            version: Версия фактов

        Returns:
            Количество фактов
        """
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()

        try:
            if transcription_id:
                query = "SELECT COUNT(*) FROM facts WHERE transcription_id = ? AND fact_version = ?"
                cursor.execute(query, (transcription_id, version))
            else:
                query = "SELECT COUNT(*) FROM facts WHERE fact_version = ?"
                cursor.execute(query, (version,))

            return cursor.fetchone()[0]

        finally:
            conn.close()

    def count_facts_sync(
        self,
        transcription_id: Optional[str] = None,
        version: str = "1.0",
    ) -> int:
        """Синхронная версия count_facts."""
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()

        try:
            if transcription_id:
                query = "SELECT COUNT(*) FROM facts WHERE transcription_id = ? AND fact_version = ?"
                cursor.execute(query, (transcription_id, version))
            else:
                query = "SELECT COUNT(*) FROM facts WHERE fact_version = ?"
                cursor.execute(query, (version,))

            return cursor.fetchone()[0]

        finally:
            conn.close()

    async def delete_facts_by_transcription(
        self,
        transcription_id: str,
        version: str = "1.0",
    ) -> int:
        """Удаление всех фактов транскрипции.

        ⚠️ ОПАСНАЯ ОПЕРАЦИЯ! Использовать только для тестов или cleanup.

        Args:
            transcription_id: ID транскрипции
            version: Версия фактов

        Returns:
            Количество удалённых фактов
        """
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()

        try:
            cursor.execute(
                "DELETE FROM facts WHERE transcription_id = ? AND fact_version = ?",
                (transcription_id, version),
            )
            deleted_count = cursor.rowcount
            conn.commit()
            return deleted_count

        except Exception as e:
            conn.rollback()
            raise e

        finally:
            conn.close()

    def delete_facts_by_transcription_sync(
        self,
        transcription_id: str,
        version: str = "1.0",
    ) -> int:
        """Синхронная версия delete_facts_by_transcription."""
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()

        try:
            cursor.execute(
                "DELETE FROM facts WHERE transcription_id = ? AND fact_version = ?",
                (transcription_id, version),
            )
            deleted_count = cursor.rowcount
            conn.commit()
            return deleted_count

        except Exception as e:
            conn.rollback()
            raise e

        finally:
            conn.close()


# ============================================================================
# EXPORTS
# ============================================================================

__all__ = ["FactStore"]
