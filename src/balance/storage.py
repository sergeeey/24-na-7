"""Balance domain storage and aggregation."""

from __future__ import annotations

import json
import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from src.storage.db import get_reflexio_db
from src.utils.date_utils import resolve_date_range

DEFAULT_DOMAINS = {
    "work": ["работа", "задача", "встреча", "проект", "клиент", "дедлайн", "банк", "безопасность"],
    "health": ["здоровье", "бег", "тренировка", "еда", "сон", "врач", "усталость", "болит"],
    "family": ["жена", "дети", "мама", "папа", "дом", "ужин", "выходные", "алматы"],
    "finance": ["деньги", "зарплата", "расходы", "кредит", "инвестиции", "тенге"],
    "psychology": ["чувствую", "тревога", "стресс", "радость", "злость", "думаю", "осознал"],
    "relations": ["друзья", "коллеги", "конфликт", "поддержка", "общение", "доверие"],
    "growth": ["учусь", "книга", "курс", "идея", "цель", "развитие", "навык"],
    "leisure": ["отдых", "кино", "игра", "прогулка", "хобби", "путешествие", "музыка"],
}


def ensure_balance_tables(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    db = get_reflexio_db(db_path)
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS domain_config (
            id TEXT PRIMARY KEY,
            domain TEXT NOT NULL UNIQUE,
            display_name TEXT NOT NULL,
            keywords_json TEXT,
            color TEXT DEFAULT '#6366f1',
            icon TEXT DEFAULT '📌',
            is_active INTEGER DEFAULT 1,
            created_at TEXT
        )
        """
    )
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_structured_events_sentiment ON structured_events(sentiment)"
    )
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_structured_events_urgency ON structured_events(urgency)"
    )
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_structured_events_created_at ON structured_events(created_at)"
    )
    try:
        se_cols = [r[1] for r in db.fetchall("PRAGMA table_info(structured_events)")]
        if se_cols and "domains" not in se_cols:
            db.execute("ALTER TABLE structured_events ADD COLUMN domains TEXT DEFAULT '[]'")
    except Exception:
        pass

    for domain, keywords in DEFAULT_DOMAINS.items():
        db.execute(
            """
            INSERT OR IGNORE INTO domain_config
            (id, domain, display_name, keywords_json, color, icon, is_active, created_at)
            VALUES (?, ?, ?, ?, ?, ?, 1, ?)
            """,
            (
                str(uuid.uuid4()),
                domain,
                domain.capitalize(),
                json.dumps(keywords, ensure_ascii=False),
                "#0ea5e9",
                "📌",
                datetime.now(timezone.utc).isoformat(),
            ),
        )
    db.conn.commit()


def get_domain_configs(db_path: Path) -> list[dict[str, Any]]:
    ensure_balance_tables(db_path)
    db = get_reflexio_db(db_path)
    rows = db.fetchall(
        "SELECT id, domain, display_name, keywords_json, color, icon, is_active, created_at FROM domain_config ORDER BY domain"
    )
    out = []
    for row in rows:
        out.append(
            {
                "id": row["id"],
                "domain": row["domain"],
                "display_name": row["display_name"],
                "keywords": json.loads(row["keywords_json"] or "[]"),
                "color": row["color"],
                "icon": row["icon"],
                "is_active": bool(row["is_active"]),
                "created_at": row["created_at"],
            }
        )
    return out


def upsert_domain_config(
    db_path: Path,
    domain: str,
    display_name: str,
    keywords: list[str],
    color: str = "#6366f1",
    icon: str = "📌",
    is_active: bool = True,
) -> None:
    ensure_balance_tables(db_path)
    db = get_reflexio_db(db_path)
    with db.transaction():
        db.execute(
            """
            INSERT INTO domain_config (id, domain, display_name, keywords_json, color, icon, is_active, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(domain) DO UPDATE SET
                display_name=excluded.display_name,
                keywords_json=excluded.keywords_json,
                color=excluded.color,
                icon=excluded.icon,
                is_active=excluded.is_active
            """,
            (
                str(uuid.uuid4()),
                domain,
                display_name,
                json.dumps(keywords, ensure_ascii=False),
                color,
                icon,
                1 if is_active else 0,
                datetime.now(timezone.utc).isoformat(),
            ),
        )


def _score_from_mentions(mentions: int, max_mentions: int) -> float:
    if max_mentions <= 0:
        return 0.0
    return round((mentions / max_mentions) * 10.0, 1)


def get_balance_wheel(db_path: Path, from_date: date, to_date: date) -> dict[str, Any]:
    """Get balance wheel data using shared calculator.

    WHY: single source of truth — same calculation for /balance/wheel and mirror.
    """
    from src.balance.calculator import calculate_balance

    ensure_balance_tables(db_path)
    db = get_reflexio_db(db_path)
    result = calculate_balance(db, from_date.isoformat(), to_date.isoformat())

    # Backward-compat response format for Android
    domains = [
        {
            "domain": d.domain,
            "mentions": d.mentions,
            "sentiment": d.avg_sentiment,
            "score": round(d.presence_score * 10.0, 1),  # 0-10 scale for legacy
            "presence_score": d.presence_score,
        }
        for d in result.domains
    ]

    alert = "Баланс в норме."
    recommendation = "Продолжай текущий ритм."
    if result.domains:
        dominant = result.domains[0]
        if dominant.mentions > max(5, result.total_mentions * 0.6):
            alert = f"Дисбаланс: домен '{dominant.domain}' доминирует в дне."
            recommendation = "Запланируй 30-60 минут на недопредставленный домен."

    has_data = bool(result.domains)
    return {
        "from": from_date.isoformat(),
        "to": to_date.isoformat(),
        "domains": domains,
        "balance_score": result.balance_score,
        "has_data": has_data,
        "covered_domains": result.covered_domains,
        "total_mentions": result.total_mentions,
        "empty_reason": None if has_data else "no_structured_events",
        "alert": alert,
        "recommendation": recommendation,
    }
