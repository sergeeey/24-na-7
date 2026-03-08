"""
Промпты для summarization с Chain of Density и Few-Shot Actions.
Reflexio 24/7 — November 2025 Integration Sprint
"""

from typing import List, Dict, Any

from src.context.optimizer import compress_for_llm


def get_chain_of_density_prompt(text: str, iterations: int = 5) -> str:
    """
    Chain of Density (CoD) промпт для постепенного уплотнения саммари.

    Args:
        text: Исходный текст для саммаризации
        iterations: Количество итераций уплотнения

    Returns:
        Промпт для LLM
    """
    # ПОЧЕМУ compress_for_llm: вместо наивной обрезки text[:4000] CCBM классифицирует
    # спаны по важности (L1-L4) и сжимает только контекстное наполнение,
    # сохраняя числа, имена, решения. Fallback на text[:4000] если CCBM недоступен.
    truncated_text = compress_for_llm(text, budget=4000)

    base_prompt = f"""Ты — эксперт по созданию информационно-плотных саммари.

Твоя задача: создать саммари текста на РУССКОМ языке, постепенно увеличивая информационную плотность.
Если текст содержит бессмысленные повторы или шум — игнорируй их.

Исходный текст:
{truncated_text}

Инструкции:
1. Начни с краткого саммари (1-2 предложения)
2. На каждой итерации добавляй конкретные детали:
   - Имена собственные
   - Числа и даты
   - Конкретные факты
   - Причинно-следственные связи
3. Сохраняй краткость, но увеличивай информационную плотность

Формат ответа (JSON):
{{
    "summary": "текст саммари",
    "density_score": 0.0-1.0,
    "entities": ["список упомянутых сущностей"],
    "key_facts": ["список ключевых фактов"]
}}

Создай {iterations} итераций, каждая более плотная, чем предыдущая.
"""
    return base_prompt


def get_few_shot_actions_prompt(text: str, examples: List[Dict[str, Any]] = None) -> str:
    """
    Few-Shot Actions промпт с примерами JSON-вывода.

    Args:
        text: Исходный текст
        examples: Список примеров (минимум 3)

    Returns:
        Промпт для LLM
    """
    if examples is None:
        examples = [
            {
                "action": "summarize",
                "output": {
                    "summary": "Краткое саммари",
                    "key_points": ["пункт 1", "пункт 2"],
                    "sentiment": "neutral",
                },
            },
            {
                "action": "extract_tasks",
                "output": {
                    "tasks": [
                        {"task": "Описание задачи", "priority": "high", "deadline": "2025-11-10"}
                    ]
                },
            },
            {
                "action": "analyze_emotions",
                "output": {"emotions": ["радость", "уверенность"], "intensity": 0.7},
            },
        ]

    examples_text = "\n\n".join(
        [
            f"Пример {i + 1}:\n{example['action']}\n{example['output']}"
            for i, example in enumerate(examples)
        ]
    )

    # ПОЧЕМУ силлогизмы (Modus Ponens): вместо расплывчатого "проанализируй текст"
    # даём LLM цепочку конкретных правил вывода: "ЕСЛИ X в тексте → ТОГДА извлеки Y".
    # Это снижает пропуск полей (Gemini "забывает" заполнить topics/emotions)
    # и повышает точность: LLM следует формальной логике, а не "интуиции".
    syllogistic_rules = """
ПРАВИЛА ИЗВЛЕЧЕНИЯ (следуй строго):

1. ЕСЛИ в тексте упоминается конкретное решение ("решил", "будем", "договорились") →
   ТОГДА извлеки его в поле "decisions" дословно.

2. ЕСЛИ в тексте есть обещание или обязательство ("надо", "обещал", "скину", "позвоню") →
   ТОГДА извлеки в "commitments": {{"person": "кому", "action": "что", "deadline": "когда/null", "context": "зачем/null"}}.
   Примеры: "надо маме позвонить", "обещал жене цветы", "скину Марату отчёт".

3. ЕСЛИ в тексте упоминается человек по имени →
   ТОГДА добавь имя в "speakers".

4. ЕСЛИ текст содержит конкретную задачу с глаголом действия ("сделать", "купить", "написать") →
   ТОГДА извлеки в "actions".

5. ЕСЛИ в тексте выражена эмоция (радость, тревога, злость, усталость и т.д.) →
   ТОГДА добавь в "emotions". Учитывай акустическую подсказку если есть.

6. ЕСЛИ ничего из вышеперечисленного не найдено → верни пустые массивы, НЕ выдумывай.
"""

    # Лимит текста для few-shot (аналогично CoD — через CCBM)
    truncated_text = compress_for_llm(text, budget=4000)

    prompt = f"""Ты — AI-ассистент для анализа текста и генерации структурированного вывода.
Отвечай на русском языке. Игнорируй бессмысленные повторы.
{syllogistic_rules}

Исходный текст:
{truncated_text}

Примеры формата вывода:

{examples_text}

Проанализируй текст по ПРАВИЛАМ ИЗВЛЕЧЕНИЯ выше и создай JSON-вывод.

Формат ответа (JSON):
{{
    "action": "тип действия",
    "output": {{
        "summary": "одно предложение о чём текст",
        "emotions": ["эмоция1", "эмоция2"],
        "topics": ["тема1", "тема2"],
        "actions": ["действие1"],
        "decisions": ["решение1"],
        "speakers": ["имя1"],
        "commitments": [{{"person": "кому", "action": "что", "deadline": null, "context": null}}],
        "urgency": "low|medium|high"
    }},
    "confidence": 0.0-1.0
}}
"""
    return prompt


def get_wow_digest_prompt(events_text: str, history_topics: list[str] | None = None) -> str:
    """
    WOW-дайджест: verdict + day_map + micro_step в ОДНОМ LLM-вызове.

    ПОЧЕМУ один вызов: заменяет extract_tasks + analyze_emotions = net -1 LLM call.
    Промпт структурирован для JSON-ответа с тремя блоками.

    Args:
        events_text: Объединённый текст транскрипций дня (уже отфильтрован от шума)
        history_topics: Темы за предыдущие 7 дней (для контекста micro_step)

    Returns:
        Промпт для LLM, ожидающий JSON-ответ
    """
    # ПОЧЕМУ compress_for_llm: WOW-дайджест получает больший бюджет (8000),
    # т.к. нужен полный контекст дня для verdict + day_map.
    truncated = compress_for_llm(events_text, budget=8000)

    history_section = ""
    if history_topics:
        history_section = (
            f"\nТемы за последние 7 дней (для контекста): {', '.join(history_topics[:20])}\n"
        )

    return f"""Ты — персональный аналитик дня. Проанализируй записи пользователя и создай WOW-дайджест на РУССКОМ языке.

Записи дня:
{truncated}
{history_section}
Создай JSON с тремя блоками:

1. **verdict** — одно яркое предложение-вердикт дня (не "день прошёл нормально", а что-то с характером). Добавь 2 короткие цитаты из текста как evidence.

2. **day_map** — карта дня из 3 ключевых точек:
   - peak: момент максимальной энергии/радости
   - valley: момент спада/тревоги/усталости
   - fork: момент выбора или решения
   Для каждой: время (примерное HH:MM), описание, эмоция.
   Если нет явного valley/fork — используй нейтральные моменты.

3. **micro_step** — ОДИН конкретный микро-шаг на завтра. Не "улучшить здоровье", а "выпить стакан воды до 10:00". Укажи domain (health/work/relationships/growth/rest).

Формат ответа (строго JSON, без markdown):
{{
    "verdict": {{
        "text": "яркий вердикт дня",
        "evidence_quotes": ["цитата 1 из записей", "цитата 2 из записей"]
    }},
    "day_map": [
        {{"type": "peak", "time": "14:30", "description": "описание момента", "emotion": "радость"}},
        {{"type": "valley", "time": "09:00", "description": "описание момента", "emotion": "усталость"}},
        {{"type": "fork", "time": "18:00", "description": "описание решения", "emotion": "решительность"}}
    ],
    "micro_step": {{
        "action": "конкретное действие на завтра",
        "why": "почему именно это",
        "domain": "health"
    }}
}}"""


def get_critic_prompt(summary: str, original_text: str) -> str:
    """
    Промпт для Critic (DeepConf валидация).

    Args:
        summary: Сгенерированное саммари
        original_text: Исходный текст

    Returns:
        Промпт для Critic
    """
    prompt = f"""Ты — критик, оценивающий качество саммари.

Исходный текст:
{original_text[:1000]}...

Сгенерированное саммари:
{summary}

Оцени саммари по следующим критериям:

1. Factual Consistency (0.0-1.0): Соответствие фактам исходного текста
2. Completeness (0.0-1.0): Полнота покрытия ключевых тем
3. Coherence (0.0-1.0): Логическая связность
4. Conciseness (0.0-1.0): Краткость без потери информации

Также рассчитай:
- Token Entropy: энтропия токенов (ниже = более предсказуемо)
- Confidence Score: общая уверенность в качестве

Формат ответа (JSON):
{{
    "factual_consistency": 0.0-1.0,
    "completeness": 0.0-1.0,
    "coherence": 0.0-1.0,
    "conciseness": 0.0-1.0,
    "token_entropy": 0.0-1.0,
    "confidence_score": 0.0-1.0,
    "issues": ["список проблем, если есть"],
    "recommendations": ["рекомендации по улучшению"]
}}
"""
    return prompt
