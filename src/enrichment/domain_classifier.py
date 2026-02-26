"""Rule-based domain classifier for Wheel of Balance."""
from __future__ import annotations

from dataclasses import dataclass
import json
import sqlite3
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class DomainRule:
    domain: str
    keywords: tuple[str, ...]


_DEFAULT_RULES = (
    DomainRule("work", ("работ", "проект", "клиент", "задач", "дедлайн", "встреч")),
    DomainRule("health", ("здоров", "сон", "пульс", "бег", "трениров", "врач")),
    DomainRule("family", ("семь", "мама", "папа", "дет", "жена", "муж")),
    DomainRule("finance", ("деньг", "бюджет", "расход", "доход", "оплат", "счёт")),
    DomainRule("psychology", ("тревог", "стресс", "эмоци", "чувств", "настроен")),
    DomainRule("relations", ("друг", "отношен", "конфликт", "команда", "партнер")),
    DomainRule("growth", ("учёб", "обуч", "развит", "книга", "курс", "навык")),
    DomainRule("leisure", ("отдых", "фильм", "музык", "хобби", "прогулк", "игра")),
)


def _normalize_keywords(keywords: Iterable[str]) -> tuple[str, ...]:
    out: list[str] = []
    for item in keywords:
        value = (item or "").strip().lower()
        if value:
            out.append(value)
    return tuple(out)


def _rules_from_db(db_path: Path | None) -> list[DomainRule]:
    if not db_path or not db_path.exists():
        return list(_DEFAULT_RULES)

    try:
        conn = sqlite3.connect(str(db_path))
        rows = conn.execute(
            "SELECT domain, keywords_json, is_active FROM domain_config WHERE is_active = 1"
        ).fetchall()
        conn.close()
    except Exception:
        return list(_DEFAULT_RULES)

    rules: list[DomainRule] = []
    for domain, keywords_json, _ in rows:
        try:
            parsed = json.loads(keywords_json or "[]")
        except Exception:
            parsed = []
        kws = _normalize_keywords(parsed)
        if domain and kws:
            rules.append(DomainRule(str(domain), kws))

    return rules or list(_DEFAULT_RULES)


def classify_domains(text: str, topics: list[str] | None = None, db_path: Path | None = None) -> list[str]:
    """Classify text/topics into Wheel-of-Balance domains (with domain_config override)."""
    source = " ".join([text or "", " ".join(topics or [])]).lower()
    rules = _rules_from_db(db_path)

    domains: list[str] = []
    for rule in rules:
        if any(keyword in source for keyword in rule.keywords):
            domains.append(rule.domain)

    if not domains and source.strip():
        domains.append("work")

    uniq: list[str] = []
    seen = set()
    for d in domains:
        if d in seen:
            continue
        uniq.append(d)
        seen.add(d)
    return uniq
