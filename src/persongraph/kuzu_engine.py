"""
KùzuDB Graph Engine — embedded граф для multi-hop запросов.

ПОЧЕМУ KùzuDB вместо NetworkX:
  - NetworkX загружает весь граф в RAM на каждый запрос
  - KùzuDB — embedded (как SQLite но для графов), Cypher, 15-188x быстрее
  - Zero infrastructure: нет отдельного сервера, хранится в директории

ПОЧЕМУ не Neo4j:
  - Neo4j требует отдельный Java-сервер (порт 7687, 512MB+ RAM)
  - Для личного приложения (10-50 персон) это избыточно

Жизненный цикл:
  При первом импорте: lazy init — создаём базу если не существует.
  Граф обновляется при каждом approval нового профиля.

Схема графа:
  NodeTable: Person(name, relationship, voice_ready)
  RelTable:  INTERACTED_WITH(from Person, to Person, count, last_date, topics)

Multi-hop запросы (через Cypher):
  MATCH (a:Person)-[:INTERACTED_WITH*1..2]-(b:Person)
  → все прямые и коллеги-коллег связи (1-2 хопа)
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Optional

from src.utils.logging import get_logger

logger = get_logger("persongraph.kuzu")


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────

def _kuzu_available() -> bool:
    """Проверяет что kuzu установлен."""
    try:
        import kuzu  # type: ignore[import-untyped]  # noqa: F401
        return True
    except ImportError:
        return False


# ──────────────────────────────────────────────
# Основной класс
# ──────────────────────────────────────────────

class KuzuGraphEngine:
    """
    Embedded граф на KùzuDB для multi-hop запросов по социальному окружению.

    Данные синхронизируются из SQLite при вызове sync_from_sqlite().
    Kuzu — read-optimized: пишем в SQLite, читаем через Kuzu.

    Использование:
        engine = KuzuGraphEngine(kuzu_dir=settings.STORAGE_PATH / "graph.kuzu")
        engine.sync_from_sqlite(sqlite_path)
        paths = engine.find_paths("Максим", "Алия", max_hops=2)
    """

    def __init__(self, kuzu_dir: Path) -> None:
        self.kuzu_dir = kuzu_dir
        self._db = None
        self._conn = None

    # ── Инициализация ──────────────────────────

    def _ensure_init(self) -> bool:
        """
        Ленивая инициализация KùzuDB.

        Returns:
            True если kuzu доступен и инициализирован, False если не установлен.
        """
        if self._conn is not None:
            return True

        if not _kuzu_available():
            logger.warning(
                "kuzu_not_available",
                hint="pip install kuzu — для multi-hop graph queries",
            )
            return False

        import kuzu  # type: ignore[import-untyped]

        self.kuzu_dir.mkdir(parents=True, exist_ok=True)
        self._db = kuzu.Database(str(self.kuzu_dir))
        self._conn = kuzu.Connection(self._db)

        self._create_schema()
        logger.info("kuzu_initialized", path=str(self.kuzu_dir))
        return True

    def _create_schema(self) -> None:
        """Создаёт схему графа если не существует."""
        # ПОЧЕМУ CREATE IF NOT EXISTS: idempotent — безопасно вызывать повторно
        self._conn.execute(  # type: ignore[union-attr]
            "CREATE NODE TABLE IF NOT EXISTS Person("
            "name STRING, relationship STRING, voice_ready BOOLEAN, PRIMARY KEY(name)"
            ")"
        )
        self._conn.execute(  # type: ignore[union-attr]
            "CREATE REL TABLE IF NOT EXISTS INTERACTED_WITH("
            "FROM Person TO Person, "
            "interaction_count INT64, "
            "last_date STRING, "
            "topics STRING"  # JSON array строкой
            ")"
        )

    # ── Синхронизация из SQLite ────────────────

    def sync_from_sqlite(self, sqlite_path: Path) -> int:
        """
        Синхронизирует данные из SQLite в KùzuDB.

        ПОЧЕМУ pull вместо push:
          SQLite — source of truth (транзакции, ACID).
          Kuzu — read-optimized projection для graph traversal.
          Синхронизируем при изменениях, не при каждой записи.

        Returns:
            Количество обновлённых персон.
        """
        if not self._ensure_init():
            return 0

        sql_conn = sqlite3.connect(str(sqlite_path), check_same_thread=False)
        sql_conn.row_factory = sqlite3.Row
        try:
            persons = sql_conn.execute(
                "SELECT name, relationship, voice_ready FROM persons"
            ).fetchall()

            count = 0
            for p in persons:
                # MERGE семантика: upsert если уже есть
                try:
                    self._conn.execute(  # type: ignore[union-attr]
                        "MERGE (p:Person {name: $name}) "
                        "SET p.relationship = $rel, p.voice_ready = $vr",
                        {
                            "name": p["name"],
                            "rel": p["relationship"] or "unknown",
                            "vr": bool(p["voice_ready"]),
                        },
                    )
                    count += 1
                except Exception:
                    # MERGE может не поддерживаться в ранних версиях — fallback
                    try:
                        self._conn.execute(  # type: ignore[union-attr]
                            "CREATE (p:Person {name: $name, relationship: $rel, voice_ready: $vr})",
                            {
                                "name": p["name"],
                                "rel": p["relationship"] or "unknown",
                                "vr": bool(p["voice_ready"]),
                            },
                        )
                        count += 1
                    except Exception:
                        pass  # уже существует

            # Синхронизируем взаимодействия
            self._sync_interactions(sql_conn)

            logger.info("kuzu_sync_done", persons=count)
            return count

        finally:
            sql_conn.close()

    def _sync_interactions(self, sql_conn: sqlite3.Connection) -> None:
        """Загружает взаимодействия из person_interactions."""
        try:
            rows = sql_conn.execute(
                """
                SELECT person_name,
                       COUNT(*) as cnt,
                       MAX(created_at) as last_date,
                       GROUP_CONCAT(topics_json) as all_topics
                FROM person_interactions
                GROUP BY person_name
                """
            ).fetchall()

            for r in rows:
                person_name = r["person_name"]
                # Пользователь = SPEAKER_0, представлен как "self" в графе
                try:
                    self._conn.execute(  # type: ignore[union-attr]
                        "MERGE (self:Person {name: 'self'}) SET self.relationship = 'self'",
                        {},
                    )
                except Exception:
                    pass

                try:
                    self._conn.execute(  # type: ignore[union-attr]
                        "MATCH (a:Person {name: 'self'}), (b:Person {name: $name}) "
                        "MERGE (a)-[r:INTERACTED_WITH]->(b) "
                        "SET r.interaction_count = $cnt, r.last_date = $dt",
                        {
                            "name": person_name,
                            "cnt": r["cnt"] or 0,
                            "dt": (r["last_date"] or "")[:10],
                        },
                    )
                except Exception:
                    pass

        except Exception as e:
            logger.warning("kuzu_sync_interactions_failed", error=str(e))

    # ── Публичный API ──────────────────────────

    def find_paths(
        self,
        from_name: str,
        to_name: str,
        max_hops: int = 2,
    ) -> list[list[str]]:
        """
        Ищет пути между двумя персонами.

        Пример: find_paths("Максим", "Алия", max_hops=2)
        → [["Максим", "self", "Алия"]] если оба общаются с пользователем

        Returns:
            Список путей (каждый путь — список имён персон).
            Пустой список если kuzu недоступен или пути нет.
        """
        if not self._ensure_init():
            return []

        try:
            result = self._conn.execute(  # type: ignore[union-attr]
                f"MATCH p = shortestPath((a:Person {{name: $from}})-"
                f"[:INTERACTED_WITH*1..{max_hops}]-(b:Person {{name: $to}})) "
                f"RETURN nodes(p)",
                {"from": from_name, "to": to_name},
            )
            paths = []
            while result.has_next():
                row = result.get_next()
                if row and row[0]:
                    path_names = [node.get("name", "?") for node in row[0]]
                    paths.append(path_names)
            return paths
        except Exception as e:
            logger.debug("kuzu_find_paths_failed", error=str(e))
            return []

    def get_neighbors(self, name: str, hops: int = 1) -> list[dict]:
        """
        Возвращает соседей персоны в графе.

        Args:
            name: Имя персоны
            hops: Глубина поиска (1 = прямые контакты, 2 = контакты контактов)

        Returns:
            Список {name, relationship, distance} или пустой список.
        """
        if not self._ensure_init():
            return []

        try:
            result = self._conn.execute(  # type: ignore[union-attr]
                f"MATCH (a:Person {{name: $name}})-[:INTERACTED_WITH*1..{hops}]-(b:Person) "
                f"WHERE b.name <> $name "
                f"RETURN DISTINCT b.name, b.relationship",
                {"name": name},
            )
            neighbors = []
            while result.has_next():
                row = result.get_next()
                neighbors.append(
                    {
                        "name": row[0],
                        "relationship": row[1] or "unknown",
                    }
                )
            return neighbors
        except Exception as e:
            logger.debug("kuzu_neighbors_failed", error=str(e))
            return []

    def get_clusters(self) -> list[list[str]]:
        """
        Находит кластеры связанных персон.

        Использует weakly connected components — группирует тех,
        кто связан хотя бы через одно взаимодействие.

        Returns:
            Список кластеров (каждый — список имён).
        """
        if not self._ensure_init():
            return []

        try:
            # Простой BFS-based clustering через Cypher
            result = self._conn.execute(  # type: ignore[union-attr]
                "MATCH (a:Person)-[:INTERACTED_WITH]-(b:Person) "
                "RETURN a.name, b.name",
                {},
            )
            # Строим граф смежности
            adjacency: dict[str, set[str]] = {}
            while result.has_next():
                row = result.get_next()
                a, b = row[0], row[1]
                adjacency.setdefault(a, set()).add(b)
                adjacency.setdefault(b, set()).add(a)

            # BFS для нахождения компонент
            visited: set[str] = set()
            clusters: list[list[str]] = []
            for node in adjacency:
                if node in visited:
                    continue
                cluster: list[str] = []
                queue = [node]
                while queue:
                    n = queue.pop(0)
                    if n in visited:
                        continue
                    visited.add(n)
                    cluster.append(n)
                    queue.extend(adjacency.get(n, set()) - visited)
                if cluster:
                    clusters.append(sorted(cluster))
            return clusters
        except Exception as e:
            logger.debug("kuzu_clusters_failed", error=str(e))
            return []

    def is_available(self) -> bool:
        """Возвращает True если KùzuDB доступен и инициализирован."""
        return self._ensure_init()


# ──────────────────────────────────────────────
# Singleton для использования в API
# ──────────────────────────────────────────────

_engine: Optional[KuzuGraphEngine] = None


def get_kuzu_engine(storage_path: Optional[Path] = None) -> KuzuGraphEngine:
    """
    Возвращает глобальный экземпляр KuzuGraphEngine (singleton).

    ПОЧЕМУ singleton: KùzuDB держит файловый lock на директорию.
    Создавать несколько Connection к одной базе не рекомендуется.
    """
    global _engine
    if _engine is None:
        if storage_path is None:
            from src.utils.config import settings
            storage_path = settings.STORAGE_PATH
        _engine = KuzuGraphEngine(kuzu_dir=storage_path / "graph.kuzu")
    return _engine
