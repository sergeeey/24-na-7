"""Chain-of-Verification (CoVe) Pipeline — hallucination detection.

4-Stage Process:
    1. Planning: Generate verification questions
    2. Execution: Answer from source only
    3. Verification: Check consistency
    4. Final: Adjust confidence scores

Использование:
    from src.digest.cove_pipeline import CoVePipeline

    pipeline = CoVePipeline(llm_client)
    verified_facts = pipeline.verify_facts(facts, context)
"""

from typing import List, Dict, Any, Optional
from dataclasses import dataclass

from src.models.fact import Fact, VerifiedFact, CoVeResult
from src.digest.validators import TranscriptionContext
from src.llm.providers import LLMClient


@dataclass
class VerificationQuestion:
    """Verification question для факта."""
    fact_id: str
    question: str
    expected_answer: str


class CoVePipeline:
    """Chain-of-Verification pipeline.

    Attributes:
        llm_client: LLM client для generation
        confidence_threshold: Минимальная confidence после CoVe
    """

    def __init__(
        self,
        llm_client: Optional[LLMClient] = None,
        confidence_threshold: float = 0.70,
    ):
        """Инициализация CoVe Pipeline.

        Args:
            llm_client: LLM client (если None — mock mode)
            confidence_threshold: Порог confidence
        """
        self.llm_client = llm_client
        self.confidence_threshold = confidence_threshold

    def verify_facts(
        self,
        facts: List[Fact],
        context: TranscriptionContext,
    ) -> List[VerifiedFact]:
        """4-stage CoVe verification.

        Args:
            facts: Список фактов для проверки
            context: Контекст транскрипции

        Returns:
            Список VerifiedFact
        """
        verified_facts = []

        for fact in facts:
            # Stage 1: Planning
            questions = self._generate_verification_questions(fact)

            # Stage 2: Execution
            answers = self._answer_from_source(questions, context)

            # Stage 3: Verification
            violations = self._verify_consistency(fact, questions, answers)

            # Stage 4: Final
            cove_result = self._create_cove_result(
                fact=fact,
                questions=questions,
                answers=answers,
                violations=violations,
            )

            # Создаём VerifiedFact
            verified_fact = VerifiedFact(
                fact_id=fact.fact_id,
                transcription_id=fact.transcription_id,
                fact_text=fact.fact_text,
                confidence_score=cove_result.adjusted_confidence,
                extraction_method="cove",
                source_span=fact.source_span,
                fact_version=fact.fact_version,
                timestamp=fact.timestamp,
                cove_result=cove_result,
            )

            # Фильтрация по threshold
            if verified_fact.confidence_score >= self.confidence_threshold:
                verified_facts.append(verified_fact)

        return verified_facts

    def _generate_verification_questions(
        self,
        fact: Fact,
    ) -> List[VerificationQuestion]:
        """Stage 1: Generate verification questions.

        Args:
            fact: Факт для проверки

        Returns:
            Список verification questions
        """
        # Mock mode
        if not self.llm_client:
            return self._mock_questions(fact)

        # LLM generation (упрощённо — в production использовать structured output)
        prompt = f"""Generate a verification question for this fact.

Fact: {fact.fact_text}

Question should:
- Be answerable from the source text
- Be specific and unambiguous
- Have yes/no or short factual answer

Output only the question, nothing else."""

        result = self.llm_client.call(prompt=prompt, max_tokens=100)
        question_text = result.get("content", result.get("text", "")).strip()

        if not question_text:
            question_text = f"Is it true that: {fact.fact_text}?"

        return [
            VerificationQuestion(
                fact_id=fact.fact_id,
                question=question_text,
                expected_answer="yes" if "?" in question_text else fact.fact_text,
            )
        ]

    def _mock_questions(self, fact: Fact) -> List[VerificationQuestion]:
        """Mock question generation."""
        return [
            VerificationQuestion(
                fact_id=fact.fact_id,
                question=f"Is it true that: {fact.fact_text}?",
                expected_answer="yes",
            )
        ]

    def _answer_from_source(
        self,
        questions: List[VerificationQuestion],
        context: TranscriptionContext,
    ) -> List[str]:
        """Stage 2: Answer questions from source only.

        Args:
            questions: Verification questions
            context: Transcription context

        Returns:
            Список ответов
        """
        answers = []

        for question in questions:
            # Mock mode
            if not self.llm_client:
                answers.append(self._mock_answer(question, context))
                continue

            # LLM answering from source
            prompt = f"""Answer this question using ONLY the information from the source text below.
If the answer is not in the source, say "NOT STATED".

Question: {question.question}

Source text:
{context.text}

Answer (be brief):"""

            result = self.llm_client.call(prompt=prompt, max_tokens=150)
            answer = result.get("content", result.get("text", "")).strip()

            answers.append(answer)

        return answers

    def _mock_answer(
        self,
        question: VerificationQuestion,
        context: TranscriptionContext,
    ) -> str:
        """Mock answer from source."""
        # Простая эвристика: проверка наличия ключевых слов
        question_lower = question.question.lower()
        context_lower = context.text.lower()

        # Извлекаем ключевые слова
        keywords = [w for w in question_lower.split() if len(w) > 3]

        matches = sum(1 for kw in keywords if kw in context_lower)

        if matches >= 2:
            return "yes"
        else:
            return "NOT STATED"

    def _verify_consistency(
        self,
        fact: Fact,
        questions: List[VerificationQuestion],
        answers: List[str],
    ) -> List[Dict[str, Any]]:
        """Stage 3: Verify consistency.

        Args:
            fact: Исходный факт
            questions: Verification questions
            answers: Ответы от LLM

        Returns:
            Список violations
        """
        violations = []

        for question, answer in zip(questions, answers):
            answer_lower = answer.lower()

            # Проверка 1: NOT STATED
            if "not stated" in answer_lower or "not in" in answer_lower:
                violations.append({
                    "severity": "HIGH",
                    "detail": f"Fact not found in source: {fact.fact_text}",
                    "question": question.question,
                    "answer": answer,
                })
                continue

            # Проверка 2: Negation mismatch
            if "no" in answer_lower or "not" in answer_lower:
                if "yes" in question.expected_answer.lower():
                    violations.append({
                        "severity": "MEDIUM",
                        "detail": f"Answer contradicts expected: {answer}",
                        "question": question.question,
                        "answer": answer,
                    })

        return violations

    def _create_cove_result(
        self,
        fact: Fact,
        questions: List[VerificationQuestion],
        answers: List[str],
        violations: List[Dict[str, Any]],
    ) -> CoVeResult:
        """Stage 4: Create CoVe result with adjusted confidence.

        Args:
            fact: Исходный факт
            questions: Verification questions
            answers: Ответы
            violations: Нарушения

        Returns:
            CoVeResult
        """
        decision = CoVeResult.decide_from_violations(violations)

        # Adjustment factors
        adjustment = 1.0
        if decision == "PASS":
            adjustment = 1.2  # Boost confidence
        elif decision == "NEEDS_REVISION":
            adjustment = 0.7  # Reduce confidence
        elif decision == "REJECT":
            adjustment = 0.3  # Heavily reduce confidence

        adjusted_confidence = min(fact.confidence_score * adjustment, 1.0)

        return CoVeResult(
            decision=decision,
            original_confidence=fact.confidence_score,
            adjusted_confidence=adjusted_confidence,
            violations=violations,
            questions=[q.question for q in questions],
            answers=answers,
            consistency_check={
                "total_questions": len(questions),
                "violations_count": len(violations),
            },
        )


# ============================================================================
# EXPORTS
# ============================================================================

__all__ = ["CoVePipeline", "VerificationQuestion"]
