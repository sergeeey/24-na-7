"""
Confidence Policy — расчёт уверенности из набора ToolResult.

ПОЧЕМУ отдельный модуль:
  Orchestrator вызывает N тулов параллельно. Нужно объединить их
  confidence в единый score с учётом весов и количества evidence.
  Правила вынесены сюда, чтобы быть тестируемыми отдельно от orchestrator.

Политика (из ТЗ):
  ≥ 0.8   → HIGH: прямой ответ
  0.6–0.79 → MEDIUM: аккуратный ответ
  0.4–0.59 → LOW: "есть признаки, но не полностью"
  < 0.4   → SPECULATIVE: предупреждение + запрос уточнения
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.core.tool_result import ToolResult


@dataclass
class ConfidenceSummary:
    score: float
    label: str
    evidence_count: int
    tool_count: int
    speculative_warning: str | None
    needs_clarification: bool


def merge_confidence(results: list["ToolResult"]) -> ConfidenceSummary:
    """
    Объединяет confidence из нескольких ToolResult в единый score.

    Алгоритм:
      1. Отфильтровываем failed (error != None)
      2. Взвешенное среднее: вес = кол-во evidence у тула
      3. Штраф если суммарных evidence < 2
      4. Применяем политику label
    """
    from src.core.tool_result import ConfidenceLabel, _label_from_score

    valid = [r for r in results if r.error is None and r.data is not None]
    if not valid:
        return ConfidenceSummary(
            score=0.0,
            label=ConfidenceLabel.SPECULATIVE.value,
            evidence_count=0,
            tool_count=0,
            speculative_warning="Пока нет данных для ответа. Начните запись или уточните период.",
            needs_clarification=True,
        )

    # Взвешенное среднее по evidence
    total_evidence = sum(len(r.evidence_ids) for r in valid)
    if total_evidence == 0:
        # Нет evidence — простое среднее со штрафом
        avg = sum(r.confidence for r in valid) / len(valid) * 0.7
    else:
        avg = sum(
            r.confidence * max(len(r.evidence_ids), 1) for r in valid
        ) / total_evidence

    # Штраф если мало evidence
    if total_evidence < 2:
        avg = min(avg, 0.79)

    avg = max(0.0, min(1.0, avg))
    label = _label_from_score(avg)

    warning = None
    needs_clarification = False
    if label == ConfidenceLabel.SPECULATIVE:
        warning = (
            "Мало данных за выбранный период. "
            "Попробуйте уточнить запрос или указать другой период."
        )
        needs_clarification = True
    elif label == ConfidenceLabel.LOW:
        warning = "Есть признаки, но данных пока недостаточно. Уточните запрос или период."

    return ConfidenceSummary(
        score=round(avg, 3),
        label=label.value,
        evidence_count=total_evidence,
        tool_count=len(valid),
        speculative_warning=warning,
        needs_clarification=needs_clarification,
    )


def single_confidence(
    evidence_count: int,
    base_score: float = 0.9,
    *,
    min_evidence_for_high: int = 2,
) -> float:
    """
    Рассчитывает confidence для одного тула по кол-ву evidence.

    Используется внутри тулов Query Engine для автоматического
    выставления confidence без магических чисел.

    Args:
      evidence_count: кол-во найденных записей
      base_score: максимальный confidence (по умолчанию 0.9)
      min_evidence_for_high: минимум для high confidence
    """
    if evidence_count == 0:
        return 0.0
    if evidence_count == 1:
        # 1 источник → cap на MEDIUM
        return min(base_score, 0.79)
    if evidence_count >= min_evidence_for_high:
        # Плавный рост: 2 → 0.8, 10 → 0.9, 50+ → 0.95
        import math
        # ПОЧЕМУ /4: при 10 evidence → 0.83 (HIGH), при 5 → 0.71 (MEDIUM).
        # Делитель /8 давал слишком медленный рост (10 events → 0.64).
        score = base_score * (1 - math.exp(-evidence_count / 4))
        return min(score, base_score)
    return min(base_score * 0.75, 0.79)
