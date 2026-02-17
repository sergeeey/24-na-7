"""Fact Extractor — извлечение atomic facts из Chain-of-Density summary.

Алгоритм (2 стадии):
    Stage 1: LLM Extraction — извлечение candidate facts из summary
    Stage 2: Source Grounding — маппинг facts к source spans через fuzzy matching

Использование:
    from src.digest.fact_extractor import FactExtractor

    extractor = FactExtractor(llm_provider)
    facts = await extractor.extract_facts(summary, transcription)
"""

import re
from typing import List, Optional, Dict, Any
from dataclasses import dataclass

try:
    from rapidfuzz import fuzz
    RAPIDFUZZ_AVAILABLE = True
except ImportError:
    RAPIDFUZZ_AVAILABLE = False

from src.models.fact import Fact, SourceSpan, create_fact_from_extraction
from src.llm.providers import LLMClient


@dataclass
class CandidateFact:
    """Кандидат на факт (перед grounding).

    Attributes:
        fact_text: Текст факта
        confidence: Предварительная уверенность от LLM
        metadata: Дополнительные метаданные
    """
    fact_text: str
    confidence: float = 0.75
    metadata: Optional[Dict[str, Any]] = None


class FactExtractor:
    """Извлечение фактов из summary с grounding в source.

    Attributes:
        llm_client: LLM client для extraction
        fuzzy_threshold: Порог для fuzzy matching (default: 0.80)
        max_facts_per_summary: Максимум фактов из одного summary
    """

    def __init__(
        self,
        llm_client: Optional[LLMClient] = None,
        fuzzy_threshold: float = 0.80,
        max_facts_per_summary: int = 20,
    ):
        """Инициализация Fact Extractor.

        Args:
            llm_client: LLM client для extraction (если None — mock mode)
            fuzzy_threshold: Порог для fuzzy matching
            max_facts_per_summary: Максимум фактов
        """
        self.llm_client = llm_client
        self.fuzzy_threshold = fuzzy_threshold
        self.max_facts_per_summary = max_facts_per_summary

    def extract_facts(
        self,
        summary: str,
        transcription_text: str,
        transcription_id: str,
    ) -> List[Fact]:
        """Извлечение фактов из summary (2 стадии).

        Args:
            summary: Chain-of-Density summary
            transcription_text: Полный текст транскрипции
            transcription_id: ID транскрипции

        Returns:
            Список grounded Fact объектов
        """
        # Stage 1: LLM Extraction
        candidate_facts = self._extract_candidate_facts(summary)

        # Stage 2: Source Grounding
        grounded_facts = []
        for candidate in candidate_facts:
            source_span = self._find_source_span(
                fact_text=candidate.fact_text,
                transcription_text=transcription_text,
                threshold=self.fuzzy_threshold,
            )

            if source_span:
                # Создаём grounded fact
                fact = create_fact_from_extraction(
                    transcription_id=transcription_id,
                    fact_text=candidate.fact_text,
                    source_text=source_span.text,
                    start_char=source_span.start_char,
                    end_char=source_span.end_char,
                    confidence=self._calculate_confidence(source_span, candidate.confidence),
                    method="cod",  # Chain-of-Density extraction
                )
                grounded_facts.append(fact)

        return grounded_facts

    def _extract_candidate_facts(self, summary: str) -> List[CandidateFact]:
        """Stage 1: Извлечение candidate facts через LLM.

        Args:
            summary: Chain-of-Density summary

        Returns:
            Список CandidateFact
        """
        # Mock mode если LLM client не задан
        if not self.llm_client:
            return self._mock_extraction(summary)

        prompt = f"""Extract atomic facts from this summary.

Rules:
- One claim per fact (no "and", no semicolons)
- Specific (no "something", "things", "maybe")
- Verifiable (not opinions)
- Maximum {self.max_facts_per_summary} facts

Summary:
{summary}

Output format (one fact per line):
- <fact 1>
- <fact 2>
...
"""

        # Вызов LLM (sync)
        result = self.llm_client.call(
            prompt=prompt,
            max_tokens=500,
        )

        response_text = result.get("content", result.get("text", ""))

        # Парсинг response
        candidates = self._parse_llm_response(response_text)

        return candidates[:self.max_facts_per_summary]

    def _mock_extraction(self, summary: str) -> List[CandidateFact]:
        """Mock extraction для тестов (без LLM).

        Args:
            summary: Summary text

        Returns:
            Список CandidateFact (пустой или из простых правил)
        """
        # Простая эвристика: split по sentences
        sentences = self._split_sentences(summary)

        candidates = []
        for sentence in sentences[:self.max_facts_per_summary]:
            if len(sentence) > 10:
                candidates.append(CandidateFact(fact_text=sentence))

        return candidates

    def _parse_llm_response(self, response: str) -> List[CandidateFact]:
        """Парсинг LLM response в CandidateFact.

        Args:
            response: Ответ от LLM (текст с bullet points)

        Returns:
            Список CandidateFact
        """
        candidates = []

        # Паттерны для bullet points
        patterns = [
            r"^-\s+(.+)$",  # - Fact
            r"^\*\s+(.+)$",  # * Fact
            r"^\d+\.\s+(.+)$",  # 1. Fact
        ]

        for line in response.strip().split("\n"):
            line = line.strip()
            if not line:
                continue

            fact_text = None
            for pattern in patterns:
                match = re.match(pattern, line)
                if match:
                    fact_text = match.group(1).strip()
                    break

            # Fallback: если не bullet point, берём всю строку
            if not fact_text and len(line) > 10:
                fact_text = line

            if fact_text:
                # Базовая фильтрация
                if len(fact_text) < 10 or len(fact_text) > 500:
                    continue

                if fact_text.endswith("."):
                    fact_text = fact_text[:-1]  # Убираем точку в конце

                candidates.append(CandidateFact(fact_text=fact_text))

        return candidates

    def _find_source_span(
        self,
        fact_text: str,
        transcription_text: str,
        threshold: float = 0.80,
    ) -> Optional[SourceSpan]:
        """Stage 2: Поиск source span через fuzzy matching.

        Args:
            fact_text: Текст факта
            transcription_text: Полная транскрипция
            threshold: Порог fuzzy matching (0.0-1.0)

        Returns:
            SourceSpan если найден, иначе None
        """
        # Метод 1: Exact substring match (быстрый)
        fact_lower = fact_text.lower()
        trans_lower = transcription_text.lower()

        # Извлекаем ключевые слова из fact_text
        keywords = self._extract_keywords(fact_text)

        # Пробуем найти подстроку с ключевыми словами
        best_span = None
        best_score = 0.0

        # Sliding window по транскрипции
        window_size = len(fact_text)
        for i in range(len(transcription_text) - window_size + 1):
            window_text = transcription_text[i:i + window_size]

            # Fuzzy matching
            score = self._fuzzy_score(fact_text, window_text)

            if score > best_score and score >= threshold:
                best_score = score
                best_span = SourceSpan(
                    start_char=i,
                    end_char=i + window_size,
                    text=window_text,
                )

        # Метод 2: Keyword-based matching (если exact не нашёл)
        if not best_span and keywords:
            best_span = self._keyword_based_matching(
                keywords=keywords,
                transcription_text=transcription_text,
                threshold=threshold,
            )

        return best_span

    def _extract_keywords(self, text: str) -> List[str]:
        """Извлечение ключевых слов из текста.

        Args:
            text: Входной текст

        Returns:
            Список ключевых слов
        """
        # Простая эвристика: слова длиной >3 букв (без stopwords)
        stopwords = {"the", "and", "that", "this", "with", "from", "have", "has", "is", "are", "was", "were"}

        words = re.findall(r"\b\w+\b", text.lower())
        keywords = [w for w in words if len(w) > 3 and w not in stopwords]

        return keywords[:5]  # Топ-5 ключевых слов

    def _keyword_based_matching(
        self,
        keywords: List[str],
        transcription_text: str,
        threshold: float = 0.80,
    ) -> Optional[SourceSpan]:
        """Поиск source span через ключевые слова.

        Args:
            keywords: Ключевые слова из факта
            transcription_text: Транскрипция
            threshold: Порог fuzzy matching

        Returns:
            SourceSpan если найден
        """
        trans_lower = transcription_text.lower()

        # Находим предложения, содержащие ключевые слова
        sentences = self._split_sentences(transcription_text)

        best_sentence = None
        best_score = 0.0

        for sentence in sentences:
            # Подсчёт ключевых слов в предложении
            keywords_found = sum(1 for kw in keywords if kw in sentence.lower())

            if keywords_found >= 2:  # Минимум 2 ключевых слова
                # Fuzzy score для sentence
                score = keywords_found / len(keywords)

                if score > best_score:
                    best_score = score
                    best_sentence = sentence

        if best_sentence and best_score >= (threshold * 0.7):  # Порог ниже для keyword matching
            # Находим позицию предложения
            start = transcription_text.find(best_sentence)
            if start >= 0:
                return SourceSpan(
                    start_char=start,
                    end_char=start + len(best_sentence),
                    text=best_sentence,
                )

        return None

    def _split_sentences(self, text: str) -> List[str]:
        """Разбивка текста на предложения.

        Args:
            text: Входной текст

        Returns:
            Список предложений
        """
        # Простая эвристика: split по . ! ?
        sentences = re.split(r"[.!?]+", text)
        return [s.strip() for s in sentences if len(s.strip()) > 10]

    def _fuzzy_score(self, text1: str, text2: str) -> float:
        """Fuzzy matching score между двумя текстами.

        Args:
            text1: Первый текст
            text2: Второй текст

        Returns:
            Similarity score (0.0-1.0)
        """
        if RAPIDFUZZ_AVAILABLE:
            return fuzz.partial_ratio(text1.lower(), text2.lower()) / 100.0
        else:
            # Fallback: простое keyword overlap
            words1 = set(re.findall(r"\b\w+\b", text1.lower()))
            words2 = set(re.findall(r"\b\w+\b", text2.lower()))

            if not words1 or not words2:
                return 0.0

            overlap = len(words1 & words2)
            union = len(words1 | words2)

            return overlap / union if union > 0 else 0.0

    def _calculate_confidence(
        self,
        source_span: SourceSpan,
        llm_confidence: float,
    ) -> float:
        """Вычисление финальной confidence на основе grounding quality.

        Args:
            source_span: Найденный source span
            llm_confidence: Исходная confidence от LLM

        Returns:
            Финальная confidence (0.0-1.0)
        """
        # Факторы confidence:
        # 1. LLM confidence (базовая)
        # 2. Длина source span (длиннее = лучше)
        # 3. Fuzzy score (если доступен)

        length_factor = min(len(source_span.text) / 50.0, 1.0)  # Нормализация по длине

        # Комбинированная confidence
        final_confidence = llm_confidence * 0.7 + length_factor * 0.3

        return min(final_confidence, 1.0)


# ============================================================================
# EXPORTS
# ============================================================================

__all__ = ["FactExtractor", "CandidateFact"]
