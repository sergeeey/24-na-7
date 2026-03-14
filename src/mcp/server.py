"""
Reflexio MCP Server — универсальная шина памяти.

ПОЧЕМУ MCP а не REST API: MCP интегрируется напрямую в Claude Desktop, Cursor,
Windsurf и любой MCP-клиент. Пользователь пишет "составь фоллоу-ап по вчерашнему
созвону" — клиент сам вызывает query_memory, находит нужный эпизод, пишет письмо.
Без плагинов, без Zapier, без копирования текста.

Запуск: python -m src.mcp.server (stdio transport, Claude Desktop подхватывает)
"""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path
from typing import Optional

import structlog
from mcp.server.fastmcp import FastMCP
from structlog.types import Processor

from src.memory.semantic_memory import retrieve_memory, record_retrieval_trace
from src.storage.db import get_reflexio_db
from src.utils.config import settings


def _configure_stdio_safe_logging() -> None:
    """Перенаправляет project logs в stderr, чтобы не ломать MCP stdio transport."""
    processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.StackInfoRenderer(),
        structlog.dev.set_exc_info,
    ]
    if settings.LOG_LEVEL == "DEBUG":
        processors.append(structlog.dev.ConsoleRenderer())
    else:
        processors.append(structlog.processors.JSONRenderer())

    log_level_map = {
        "DEBUG": 10,
        "INFO": 20,
        "WARNING": 30,
        "ERROR": 40,
        "CRITICAL": 50,
    }
    min_level = log_level_map.get(settings.LOG_LEVEL.upper(), 20)

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(min_level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
        cache_logger_on_first_use=True,
    )


_configure_stdio_safe_logging()

mcp = FastMCP(
    "reflexio-memory",
)


def _db_path() -> Path:
    return settings.STORAGE_PATH / "reflexio.db"


def _table_exists(table_name: str) -> bool:
    db = get_reflexio_db(_db_path())
    row = db.fetchone(
        """
        SELECT name
        FROM sqlite_master
        WHERE type = 'table' AND name = ?
        """,
        (table_name,),
    )
    return row is not None


@mcp.tool()
def query_memory(query: str, limit: int = 5) -> str:
    """Семантический поиск по цифровой памяти Reflexio.

    Ищет по всей истории разговоров, заметок, эмоций и тем.
    Примеры запросов:
    - "О чём я говорил с Маратом в январе?"
    - "Какие решения я принял на прошлой неделе?"
    - "Когда я последний раз обсуждал бюджет?"

    Args:
        query: Что искать в памяти (естественный язык)
        limit: Максимум результатов (1-20)
    """
    limit = max(1, min(limit, 20))
    db_path = _db_path()

    results = retrieve_memory(db_path, query, top_k=limit)

    if not results:
        # Fallback: fulltext поиск в structured_events
        import sqlite3 as _sqlite3

        try:
            con = _sqlite3.connect(_db_path())
            con.row_factory = _sqlite3.Row
            words = [w for w in query.split() if len(w) > 2]
            like_clause = " OR ".join(["text LIKE ?" for _ in words])
            params = [f"%{w}%" for w in words]
            rows = con.execute(
                f"SELECT timestamp, text, emotions, topics, summary FROM structured_events "
                f"WHERE is_current = 1 AND ({like_clause}) ORDER BY timestamp DESC LIMIT ?",
                params + [limit],
            ).fetchall()
            con.close()
            if rows:
                lines = []
                for i, r in enumerate(rows, 1):
                    t = dict(r)
                    lines.append(
                        f"{i}. [{t['timestamp'][:10]}]\n   {(t.get('summary') or t.get('text',''))[:200]}"
                    )
                return "\n\n".join(lines)
        except Exception:
            pass
        return "Ничего не найдено в памяти по этому запросу."

    # Trace для аудируемости
    node_ids = [r["node_id"] for r in results]
    record_retrieval_trace(db_path, query, node_ids, limit)

    # Форматируем для LLM-клиента
    lines = []
    for i, r in enumerate(results, 1):
        summary = r.get("summary") or r.get("content", "")[:200]
        topics = r.get("topics", [])
        created = r.get("created_at", "")[:10]
        score = r.get("score", 0)

        line = f"{i}. [{created}] (relevance: {score:.2f})\n   {summary}"
        if topics:
            line += f"\n   Темы: {', '.join(topics[:5])}"
        lines.append(line)

    return "\n\n".join(lines)


@mcp.tool()
def get_digest(target_date: Optional[str] = None) -> str:
    """Получить дайджест дня — сводку всех разговоров, эмоций и решений.

    Args:
        target_date: Дата в формате YYYY-MM-DD. Если не указана — сегодня.
    """
    if target_date is None:
        target_date = date.today().isoformat()

    db = get_reflexio_db(_db_path())

    if not _table_exists("digest_cache"):
        return "Таблица digest_cache отсутствует. Дайджесты ещё не инициализированы."

    row = db.fetchone(
        """
        SELECT digest_json, generated_at, status
        FROM digest_cache
        WHERE date = ?
        ORDER BY generated_at DESC
        LIMIT 1
        """,
        (target_date,),
    )

    if not row:
        # Fallback: вернуть последний доступный дайджест
        row = db.fetchone(
            """
            SELECT digest_json, generated_at, status, date
            FROM digest_cache
            WHERE status = 'ready'
            ORDER BY date DESC
            LIMIT 1
            """,
        )
        if not row:
            return f"Дайджест за {target_date} не найден. Возможно, за этот день не было записей."
        target_date = row["date"]

    payload = {}
    try:
        payload = json.loads(row["digest_json"] or "{}")
    except Exception:
        payload = {}

    parts = [f"# Дайджест за {target_date}\n"]

    summary = payload.get("summary_text") or ""
    if summary:
        parts.append(f"## Сводка\n{summary}")

    stats = (
        f"Записей: {payload.get('total_recordings', 0)}, "
        f"источников: {payload.get('sources_count', 0)}, "
        f"длительность: {payload.get('total_duration', '—')}"
    )
    parts.append(stats)

    themes = payload.get("key_themes") or []
    if themes:
        parts.append(f"## Темы\n{', '.join(themes)}")

    emotions = payload.get("emotions") or []
    if emotions:
        parts.append(f"## Эмоции\n{', '.join(emotions)}")

    actions = payload.get("actions") or []
    if actions:
        action_lines = []
        for a in actions:
            if isinstance(a, dict):
                status = "done" if a.get("done") else "open"
                action_lines.append(f"- [{status}] {a.get('text', '')}")
            else:
                action_lines.append(f"- {a}")
        if action_lines:
            parts.append("## Намерения\n" + "\n".join(action_lines))

    verdict = payload.get("verdict") or {}
    if isinstance(verdict, dict) and verdict.get("text"):
        parts.append(f"## Вердикт\n{verdict['text']}")

    return "\n\n".join(parts)


@mcp.tool()
def list_persons(limit: int = 20) -> str:
    """Список людей из социального графа Reflexio.

    Показывает людей, которых система распознала в разговорах:
    имя, тип связи, готовность голосового профиля, последнее упоминание.

    Args:
        limit: Максимум результатов (1-50)
    """
    limit = max(1, min(limit, 50))
    db = get_reflexio_db(_db_path())

    if not _table_exists("persons"):
        return "В социальном графе пока нет людей."

    rows = db.fetchall(
        """
        SELECT name, relationship, voice_ready, sample_count, last_seen
        FROM persons
        ORDER BY last_seen DESC
        LIMIT ?
        """,
        (limit,),
    )

    if not rows:
        return "В социальном графе пока нет людей."

    lines = []
    for r in rows:
        name = r["name"]
        rel = r["relationship"] or "—"
        voice = "voice ready" if r["voice_ready"] else "no voice"
        samples = r["sample_count"] or 0
        seen = (r["last_seen"] or "")[:10]

        line = f"- **{name}** ({rel}, {voice}, samples: {samples})"
        if seen:
            line += f" — last seen {seen}"
        lines.append(line)

    return "\n".join(lines)


@mcp.tool()
def get_commitments(status: str = "open", limit: int = 10) -> str:
    """Список обязательств и обещаний, извлечённых из разговоров.

    Args:
        status: Фильтр: "open" (невыполненные), "done" (выполненные), "all"
        limit: Максимум результатов (1-30)
    """
    limit = max(1, min(limit, 30))
    db = get_reflexio_db(_db_path())

    if not _table_exists("episodes"):
        return "Таблица episodes отсутствует. Обязательства ещё не доступны."

    rows = db.fetchall(
        """
        SELECT commitments_json, day_key
        FROM episodes
        WHERE commitments_json IS NOT NULL AND commitments_json != '[]'
        ORDER BY day_key DESC
        LIMIT 100
        """,
    )

    extracted: list[dict[str, str | bool]] = []
    for row in rows:
        try:
            commitments = json.loads(row["commitments_json"] or "[]")
        except Exception:
            continue
        for item in commitments:
            if isinstance(item, dict):
                done = bool(item.get("done", False))
                if status == "done" and not done:
                    continue
                if status == "open" and done:
                    continue
                extracted.append(
                    {
                        "text": str(item.get("text") or "").strip(),
                        "person": str(item.get("person") or "").strip(),
                        "due": str(item.get("due_date") or item.get("due") or "").strip(),
                        "done": done,
                        "source": str(row["day_key"] or "").strip(),
                    }
                )
            elif item:
                extracted.append(
                    {
                        "text": str(item).strip(),
                        "person": "",
                        "due": "",
                        "done": False,
                        "source": str(row["day_key"] or "").strip(),
                    }
                )

    extracted = [item for item in extracted if item["text"]][:limit]

    if not extracted:
        return f"Нет обязательств со статусом '{status}'."

    lines = []
    for item in extracted:
        check = "x" if item["done"] else " "
        line = f"- [{check}] {item['text']}"
        if item["person"]:
            line += f" (@{item['person']})"
        if item["due"]:
            line += f" — due: {item['due']}"
        if item["source"]:
            line += f" [from {item['source']}]"
        lines.append(line)

    return "\n".join(lines)


if __name__ == "__main__":
    mcp.run()
