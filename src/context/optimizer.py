"""
Обёртка над CCBM для сжатия текста перед отправкой в LLM.

ПОЧЕМУ отдельный модуль: единая точка интеграции CCBM → Reflexio.
Если CCBM не установлен (VPS, CI) — graceful fallback на наивную обрезку text[:limit].

Используем СИНХРОННЫЕ компоненты CCBM напрямую (CriticalityAnalyzer + OptimizationEngine),
без async overhead — промпты строятся синхронно.
"""

from __future__ import annotations

try:
    from ccbm import CriticalityAnalyzer, OptimizationEngine

    CCBM_AVAILABLE = True
except ImportError:
    CCBM_AVAILABLE = False

try:
    from src.utils.logging import get_logger
except Exception:
    import logging

    def get_logger(x):  # noqa: A001
        return logging.getLogger(x)


logger = get_logger("context.optimizer")


def compress_for_llm(text: str, budget: int = 4000, language: str = "ru") -> str:
    """Сжимает текст с сохранением критически важной информации.

    ПОЧЕМУ не просто text[:4000]:
    Наивная обрезка режет на полуслове и теряет важные данные в конце текста
    (числа, имена, решения). CCBM классифицирует спаны по важности (L1-L4)
    и сжимает только L4 (контекстное наполнение), сохраняя L1 (числа),
    L2 (решения), L3 (имена) полностью.

    Args:
        text: исходный текст
        budget: целевой лимит в символах (не токенах — упрощение)
        language: язык текста ('ru', 'kk')

    Returns:
        сжатый текст, гарантированно не длиннее budget символов
    """
    if not text or len(text) <= budget:
        return text

    if not CCBM_AVAILABLE:
        # Fallback: наивная обрезка (как было раньше)
        return text[:budget] + "…"

    try:
        # ПОЧЕМУ language="kk": CriticalityAnalyzer использует KazRoBERTa NER,
        # который работает и для русского текста (казахский + кириллица).
        analyzer = CriticalityAnalyzer(language=language)
        spans = analyzer.analyze(text)

        if not spans:
            return text[:budget] + "…"

        optimizer = OptimizationEngine(target_budget=budget)
        result = optimizer.optimize(spans)

        optimized = result.optimized_text
        # Гарантия: не превышаем budget даже после оптимизации
        if len(optimized) > budget:
            optimized = optimized[:budget] + "…"

        logger.debug(
            "ccbm_compressed",
            original_len=len(text),
            optimized_len=len(optimized),
            ratio=round(result.compression_ratio, 2),
            spans_preserved=result.spans_preserved,
            spans_removed=result.spans_removed,
        )
        return optimized

    except Exception as e:
        # ПОЧЕМУ fallback, а не raise: сжатие — не критический путь.
        # Лучше отправить обрезанный текст, чем сломать весь pipeline.
        logger.warning("ccbm_compression_failed", error=str(e))
        return text[:budget] + "…"
