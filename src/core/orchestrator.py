"""
Orchestrator — автоматический выбор тулов + параллельный вызов + синтез.

ПОЧЕМУ нужен:
  Пользователь задаёт вопрос на естественном языке. Без orchestrator
  клиент должен сам выбрать нужный endpoint — это нарушает принцип
  "One Interface". Orchestrator анализирует интент и вызывает нужные
  тулы, скрывая детали от пользователя.

Pipeline:
  1. IntentAnalyzer → список тулов + параметры (rule-based, без LLM)
  2. Параллельный вызов тулов через asyncio.gather
  3. merge_confidence → единый confidence score
  4. ResponseSynthesizer → текстовый ответ (минимальный)

Архитектура — rule-based intent (не LLM):
  LLM для intent analysis = дополнительная задержка 300-800ms.
  Rule-based даёт <5ms и покрывает 90% вопросов.
  При "непонятном" запросе → fallback на query_events.
"""
from __future__ import annotations

import asyncio
import re
import time
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from src.core.tool_result import ToolResult
from src.core.confidence import merge_confidence, ConfidenceSummary
from src.utils.logging import get_logger

logger = get_logger("core.orchestrator")

# ─────────────────────────────────────────────────────────────────────────────
# Intent Analysis (rule-based)
# ─────────────────────────────────────────────────────────────────────────────

_DIGEST_KEYWORDS = re.compile(
    r"дайджест|итог|summary|за день|сегодня|вчера|что было|recap|обзор",
    re.IGNORECASE,
)
_PERSON_KEYWORDS = re.compile(
    r"(?:о|про|с|насчёт)\s+([А-ЯЁа-яёA-Za-z]{2,})|([А-ЯЁ][а-яё]{2,})\s+(?:говорил|сказал|писал|звонил)",
    re.IGNORECASE,
)
# Стоп-слова которые не являются именами персон
_PERSON_STOPWORDS = frozenset({
    "было", "чём", "ком", "чем", "том", "сём", "всём", "этом",
    "работе", "доме", "деле", "мне", "тебе", "нас", "них",
    "здоровье", "стрессе", "времени", "дне", "неделе", "месяце",
})
_HEALTH_KEYWORDS = re.compile(
    r"здоровь|стресс|сон|энергия|усталост|самочувстви|настроени|тревог",
    re.IGNORECASE,
)
_TASK_KEYWORDS = re.compile(
    r"задач|todo|сделать|не забыть|план|дедлайн|deadline|напомни",
    re.IGNORECASE,
)
_EMOTION_KEYWORDS = re.compile(
    r"эмоци|чувств|настрое|тревог|радост|злост|грустн|счастл",
    re.IGNORECASE,
)
_DATE_PATTERN = re.compile(r"\d{4}-\d{2}-\d{2}")
_DAYS_BACK_PATTERN = re.compile(r"за\s+(\d+)\s+дн|последни[еx]\s+(\d+)\s+дн", re.IGNORECASE)


@dataclass
class ToolCall:
    """Описание вызова тула с параметрами."""
    tool: str
    params: dict[str, Any] = field(default_factory=dict)


def analyze_intent(question: str) -> list[ToolCall]:
    """
    Rule-based анализ вопроса → список ToolCall.

    Покрывает ~90% вопросов без LLM. Latency <5ms.
    """
    calls: list[ToolCall] = []

    # Извлекаем дату/период из вопроса
    date_match = _DATE_PATTERN.search(question)
    days_match = _DAYS_BACK_PATTERN.search(question)

    date_param = date_match.group(0) if date_match else None
    days_param = int(days_match.group(1) or days_match.group(2)) if days_match else None

    # Проверяем вчера/сегодня
    if "вчера" in question.lower():
        from datetime import date, timedelta
        date_param = (date.today() - timedelta(days=1)).isoformat()

    base_params: dict[str, Any] = {}
    if date_param:
        base_params["date"] = date_param
    elif days_param:
        base_params["days_back"] = days_param

    # Персона?
    person_match = _PERSON_KEYWORDS.search(question)
    if person_match:
        name = person_match.group(1) or person_match.group(2)
        if name and name.lower() not in _PERSON_STOPWORDS:
            calls.append(ToolCall("get_person_insights", {"name": name}))

    # Дайджест?
    if _DIGEST_KEYWORDS.search(question):
        calls.append(ToolCall("get_digest", base_params))

    # Здоровье/баланс?
    if _HEALTH_KEYWORDS.search(question):
        calls.append(ToolCall("query_events", {**base_params, "q": question, "topics": "здоровье,стресс,сон"}))

    # Эмоции?
    if _EMOTION_KEYWORDS.search(question):
        calls.append(ToolCall("query_events", {**base_params, "q": question}))

    # Задачи?
    if _TASK_KEYWORDS.search(question):
        calls.append(ToolCall("query_events", {**base_params, "q": question, "topics": "задача,план"}))

    # Fallback — семантический поиск по вопросу
    if not calls:
        calls.append(ToolCall("query_events", {**base_params, "q": question}))

    # Дедупликация одинаковых тулов
    seen: set[str] = set()
    unique: list[ToolCall] = []
    for c in calls:
        key = f"{c.tool}:{sorted(c.params.items())}"
        if key not in seen:
            seen.add(key)
            unique.append(c)

    return unique


# ─────────────────────────────────────────────────────────────────────────────
# Tool Executor
# ─────────────────────────────────────────────────────────────────────────────

async def _execute_tool(call: ToolCall) -> ToolResult:
    """Вызывает один тул по имени с параметрами."""
    try:
        if call.tool == "query_events":
            from src.api.routers.query import query_events
            raw = await query_events(
                q=call.params.get("q", ""),
                date=call.params.get("date"),
                days_back=call.params.get("days_back"),
                topics=call.params.get("topics"),
                emotions=call.params.get("emotions"),
                min_confidence=0.0,
                limit=call.params.get("limit", 20),
                include_evidence=True,
            )
            return _dict_to_tool_result(raw, "query_events")

        elif call.tool == "get_digest":
            from src.api.routers.query import get_digest
            raw = await get_digest(
                date=call.params.get("date"),
                # ПОЧЕМУ True: оркестратор внутренний — ему нужны evidence_ids
                # для merge_confidence. Без них confidence всегда "low".
                include_evidence=True,
            )
            return _dict_to_tool_result(raw, "get_digest")

        elif call.tool == "get_person_insights":
            from src.api.routers.query import get_person_insights
            raw = await get_person_insights(
                name=call.params["name"],
                include_evidence=False,
            )
            return _dict_to_tool_result(raw, "get_person_insights")

        else:
            return ToolResult.error_result(call.tool, f"Unknown tool: {call.tool}")

    except Exception as e:
        logger.error("tool_execution_failed", tool=call.tool, error=str(e))
        return ToolResult.error_result(call.tool, str(e))


def _dict_to_tool_result(d: dict, tool_name: str) -> ToolResult:
    """Конвертирует API dict обратно в ToolResult для merge_confidence."""
    # ПОЧЕМУ evidence_ids из dict: без них merge_confidence считает evidence=0
    # и всегда возвращает "low" confidence, даже если данные есть.
    evidence_ids = d.get("evidence_ids", [])
    if not evidence_ids:
        # Fallback: считаем по evidence_metadata
        evidence_ids = [m.get("id", "") for m in d.get("evidence_metadata", []) if m.get("id")]
    return ToolResult(
        data=d.get("data"),
        evidence_ids=evidence_ids,
        confidence=d.get("confidence", 0.0),
        tool_name=tool_name,
        db_query_ms=d.get("db_query_ms", 0.0),
        error=d.get("error"),
        warning=d.get("warning"),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Response Synthesis
# ─────────────────────────────────────────────────────────────────────────────

def _extract_top_topics(events: list[dict], limit: int = 3) -> list[str]:
    """Извлекает top-N тем из списка событий (Counter по topics_json)."""
    import json as _json
    counter: Counter = Counter()
    for ev in events:
        raw = ev.get("topics_json", "")
        if not raw:
            continue
        try:
            topics = _json.loads(raw) if isinstance(raw, str) else raw
            if isinstance(topics, list):
                for t in topics:
                    if isinstance(t, str) and t.strip():
                        counter[t.strip()] += 1
        except (ValueError, TypeError):
            pass
    return [t for t, _ in counter.most_common(limit)]


def _dominant_sentiment(events: list[dict]) -> str | None:
    """Определяет доминирующий sentiment из списка событий."""
    counter: Counter = Counter()
    for ev in events:
        s = ev.get("sentiment", "")
        if s:
            counter[s] += 1
    if not counter:
        return None
    return counter.most_common(1)[0][0]


def synthesize_response(
    question: str,
    results: list[ToolResult],
    confidence: ConfidenceSummary,
) -> tuple[str, str | None]:
    """
    Meaning-first текстовый ответ + primary_tool.

    ПОЧЕМУ meaning-first:
      Старая версия показывала инфраструктуру ("Дайджест найден. Источников: 6.").
      Пользователю нужен СМЫСЛ ("День прошёл спокойно, но с рабочим напряжением").
      Все данные уже есть в data — извлекаем verdict/summary/top_topics.

    Returns:
        (answer_text, primary_tool)
    """
    parts: list[str] = []
    primary_tool: str | None = None

    # Предупреждение при низкой уверенности
    if confidence.speculative_warning:
        parts.append(f"⚠️ {confidence.speculative_warning}")

    # Если нет данных
    valid = [r for r in results if r.data is not None and r.error is None]
    if not valid:
        return ("Данных по этому запросу не найдено. Попробуйте изменить период или формулировку.", None)

    # ПОЧЕМУ приоритет digest > person > events:
    # Дайджест содержит осмысленный verdict от LLM, это самый rich ответ.
    # Персона — конкретный запрос. Events — fallback.
    tool_names = [r.tool_name for r in valid]

    if "get_digest" in tool_names:
        primary_tool = "get_digest"
        for r in valid:
            if r.tool_name != "get_digest" or not r.data:
                continue
            data = r.data
            # Извлекаем verdict.text → fallback summary_text → fallback мета
            verdict = data.get("verdict")
            if isinstance(verdict, dict) and verdict.get("text"):
                parts.append(verdict["text"])
            elif data.get("summary_text"):
                parts.append(data["summary_text"])
            else:
                date_str = data.get("date", "")
                parts.append(f"Дайджест за {date_str}." if date_str else "Дайджест найден.")
            break

    elif "get_person_insights" in tool_names:
        primary_tool = "get_person_insights"
        for r in valid:
            if r.tool_name == "get_person_insights" and r.data:
                name = (r.data.get("person") or {}).get("name", "")
                count = r.data.get("interactions_count", 0)
                parts.append(f"Персона {name}: {count} взаимодействий.")
                break

    elif "query_events" in tool_names:
        primary_tool = "query_events"
        for r in valid:
            if r.tool_name != "query_events" or not r.data:
                continue
            events = r.data.get("events", [])
            total = r.data.get("total", len(events))
            top = _extract_top_topics(events)
            if top:
                parts.append(f"Найдено {total} событий. Основные темы: {', '.join(top)}.")
            else:
                parts.append(f"Найдено {total} событий по запросу.")
            break

    return (" ".join(parts) if parts else "Результат получен.", primary_tool)


# ─────────────────────────────────────────────────────────────────────────────
# Main Orchestrator
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class OrchestratorResponse:
    """Финальный ответ оркестратора."""
    answer: str
    data: list[dict]           # данные от каждого тула
    confidence: float
    confidence_label: str
    evidence_count: int
    tools_used: list[str]
    total_ms: float
    needs_clarification: bool
    warning: str | None
    primary_tool: str | None   # какой тул дал основной ответ (для rich rendering)


async def orchestrate(question: str) -> OrchestratorResponse:
    """
    Главная функция — принимает вопрос, возвращает структурированный ответ.

    Используется в POST /ask endpoint.
    Latency target: ≤400ms (без LLM-запросов).
    """
    t0 = time.perf_counter()

    # 1. Анализ интента
    calls = analyze_intent(question)
    logger.info("orchestrator_intent", question=question[:60], tools=[c.tool for c in calls])

    # 2. Параллельный вызов тулов
    results = await asyncio.gather(*[_execute_tool(c) for c in calls])
    results = list(results)

    # 3. Merge confidence
    conf_summary = merge_confidence(results)

    # 4. Синтез ответа (meaning-first)
    answer, primary_tool = synthesize_response(question, results, conf_summary)

    total_ms = (time.perf_counter() - t0) * 1000

    logger.info(
        "orchestrator_done",
        tools_used=[c.tool for c in calls],
        primary_tool=primary_tool,
        confidence=conf_summary.score,
        evidence=conf_summary.evidence_count,
        total_ms=round(total_ms, 1),
    )

    return OrchestratorResponse(
        answer=answer,
        data=[r.to_api_dict() for r in results],
        confidence=conf_summary.score,
        confidence_label=conf_summary.label,
        evidence_count=conf_summary.evidence_count,
        tools_used=[c.tool for c in calls],
        total_ms=round(total_ms, 1),
        needs_clarification=conf_summary.needs_clarification,
        warning=conf_summary.speculative_warning,
        primary_tool=primary_tool,
    )
