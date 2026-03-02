"""Генератор дайджестов из транскриптов с улучшенным summarization."""
from datetime import date, datetime
from pathlib import Path
from typing import Optional, Dict, List
import json

from src.storage.db import get_reflexio_db
from src.utils.config import settings
from src.utils.logging import setup_logging, get_logger
from src.digest.metrics_ext import calculate_extended_metrics
from src.storage.ingest_persist import ensure_ingest_tables
from src.memory.core_memory import get_core_memory
from src.memory.session_memory import get_session_memory

# Новые модули summarization (November 2025 Integration Sprint)
try:
    from src.summarizer.chain_of_density import generate_dense_summary
    from src.summarizer.critic import validate_summary
    from src.summarizer.few_shot import extract_tasks, analyze_emotions
    SUMMARIZER_AVAILABLE = True
except ImportError:
    SUMMARIZER_AVAILABLE = False
    logger = get_logger("digest")
    logger.warning("summarizer_modules_not_available", using_basic_summary=True)

setup_logging()
logger = get_logger("digest")


class DigestGenerator:
    """Генерирует дайджест дня из транскриптов."""

    # ПОЧЕМУ фильтрация: Whisper транскрибирует фоновый шум как "you", "the", пустые строки.
    # 10 000+ мусорных записей → LLM галлюцинирует на корейском/грузинском.
    # Фильтруем до отправки в LLM: минимум 3 слова, не стоп-фразы, language_probability > 0.4.
    NOISE_PHRASES = frozenset({
        "you", "the", "a", "an", "i", "he", "she", "it", "we", "they",
        "yes", "no", "oh", "ah", "um", "uh", "hmm", "huh",
        "that's it", "thank you", "thanks", "okay", "ok",
        "угу", "ага", "ну", "мм", "хм", "это", "ладно", "понял", "окей",
    })
    MIN_WORDS = 3
    MIN_LANG_PROBABILITY = 0.4
    MAX_TRANSCRIPTIONS_FOR_LLM = 100  # Лимит записей для LLM-задач (extract_facts)
    MAX_TEXT_LENGTH_FOR_LLM = 16000  # Tiered CoD вход для дневного дайджеста
    MAX_HOURLY_CHUNK_CHARS = 6000

    def __init__(self, db_path: Optional[Path] = None):
        """Инициализация генератора."""
        if db_path is None:
            db_path = settings.STORAGE_PATH / "reflexio.db"
        self.db_path = db_path
        self.digests_dir = Path("digests")
        self.digests_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _is_meaningful(text: str, lang_prob: float = 1.0) -> bool:
        """Проверяет, содержит ли транскрипция осмысленный текст."""
        text = text.strip()
        if not text:
            return False
        words = text.split()
        if len(words) < DigestGenerator.MIN_WORDS:
            return False
        if text.lower() in DigestGenerator.NOISE_PHRASES:
            return False
        if lang_prob < DigestGenerator.MIN_LANG_PROBABILITY:
            return False
        return True

    @staticmethod
    def _has_cyrillic(text: str) -> bool:
        """Проверяет, содержит ли текст кириллицу (русский)."""
        return any('\u0400' <= c <= '\u04ff' for c in text)

    @staticmethod
    def _hour_bucket(iso_ts: str | None) -> str:
        """Нормализует timestamp в бакет YYYY-MM-DD HH:00."""
        if not iso_ts:
            return "unknown"
        try:
            dt = datetime.fromisoformat(str(iso_ts).replace("Z", "+00:00"))
            return dt.strftime("%Y-%m-%d %H:00")
        except Exception:
            return "unknown"

    def _iter_meaningful_texts(self, transcriptions: List[Dict]) -> List[str]:
        """Фильтрует осмысленные тексты без обрезки по длине."""
        meaningful: List[str] = []
        for t in transcriptions:
            text = (t.get("text") or "").strip()
            lang_prob = t.get("language_probability") or 1.0
            if self._is_meaningful(text, lang_prob):
                meaningful.append(text)
        return meaningful

    def _join_meaningful_text(
        self,
        transcriptions: List[Dict],
        max_transcriptions: Optional[int],
        max_chars: Optional[int],
    ) -> str:
        """Собирает осмысленный текст с опциональными лимитами."""
        meaningful = self._iter_meaningful_texts(transcriptions)
        if max_transcriptions:
            meaningful = meaningful[-max_transcriptions:]
        joined = " ".join(meaningful)
        if max_chars and len(joined) > max_chars:
            joined = joined[-max_chars:]
        return joined

    def _get_meaningful_text(self, transcriptions: List[Dict]) -> str:
        """Собирает осмысленный текст для LLM-задач с ограничением бюджета."""
        return self._join_meaningful_text(
            transcriptions,
            max_transcriptions=self.MAX_TRANSCRIPTIONS_FOR_LLM,
            max_chars=self.MAX_TEXT_LENGTH_FOR_LLM,
        )

    def _build_tiered_digest_input(self, transcriptions: List[Dict]) -> str:
        """Строит вход для дневного CoD: либо полный текст, либо summary-of-summaries по часам."""
        full_text = self._join_meaningful_text(
            transcriptions,
            max_transcriptions=None,
            max_chars=None,
        )
        if not full_text:
            return ""

        if len(full_text) <= self.MAX_TEXT_LENGTH_FOR_LLM:
            return full_text

        # Fallback без summarizer: ограничиваемся хвостом дня.
        if not SUMMARIZER_AVAILABLE:
            return full_text[-self.MAX_TEXT_LENGTH_FOR_LLM:]

        grouped: Dict[str, List[Dict]] = {}
        for t in transcriptions:
            bucket = self._hour_bucket(t.get("created_at"))
            grouped.setdefault(bucket, []).append(t)

        hourly_summaries: List[str] = []
        for hour in sorted(grouped.keys()):
            chunk_text = self._join_meaningful_text(
                grouped[hour],
                max_transcriptions=None,
                max_chars=self.MAX_HOURLY_CHUNK_CHARS,
            )
            if not chunk_text:
                continue
            try:
                dense = generate_dense_summary(chunk_text, iterations=1)
                summary = (dense.get("summary") or "").strip()
            except Exception as e:
                logger.warning("hourly_cod_failed", hour=hour, error=str(e))
                summary = ""

            if not summary:
                summary = chunk_text[:1000]
            hourly_summaries.append(f"[{hour}] {summary}")

        if not hourly_summaries:
            return full_text[-self.MAX_TEXT_LENGTH_FOR_LLM:]

        tiered = "\n".join(hourly_summaries)
        if len(tiered) > self.MAX_TEXT_LENGTH_FOR_LLM:
            tiered = tiered[-self.MAX_TEXT_LENGTH_FOR_LLM:]
        return tiered

    def get_transcriptions(self, target_date: date) -> List[Dict]:
        """
        Получает все транскрипции за день.
        
        Args:
            target_date: Дата для выборки
            
        Returns:
            Список транскрипций с метаданными
        """
        if not self.db_path.parent.exists():
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
        ensure_ingest_tables(self.db_path)
        if not self.db_path.exists():
            logger.warning("database_not_found", db_path=str(self.db_path))
            return []
        db = get_reflexio_db(self.db_path)

        # ПОЧЕМУ is_user фильтр: после включения Speaker Verification дайджест
        # должен содержать только речь пользователя, не фоновый TV/радио.
        # DEFAULT 1 в схеме гарантирует backward-compatibility (старые записи = user).
        # Когда SPEAKER_VERIFICATION_ENABLED=False — всё is_user=1, фильтр без эффекта.
        speaker_filter = (
            "AND (t.is_user = 1 OR t.is_user IS NULL)"
            if settings.SPEAKER_VERIFICATION_ENABLED
            else ""
        )

        # Получаем транскрипции за день
        rows = db.fetchall(f"""
            SELECT
                t.id,
                t.ingest_id,
                t.text,
                t.language,
                t.language_probability,
                t.duration,
                t.segments,
                t.created_at,
                i.filename,
                i.file_size
            FROM transcriptions t
            LEFT JOIN ingest_queue i ON t.ingest_id = i.id
            WHERE DATE(t.created_at) = ? {speaker_filter}
            ORDER BY t.created_at ASC
        """, (target_date.isoformat(),))  # nosec B608 — speaker_filter is a hardcoded literal string, date is parameterized

        transcriptions = [dict(row) for row in rows]

        logger.info(
            "transcriptions_found",
            date=target_date.isoformat(),
            count=len(transcriptions),
        )

        return transcriptions
    
    def extract_facts(self, transcriptions: List[Dict], use_llm: bool = True) -> List[Dict]:
        """
        Извлекает факты из транскрипций с улучшенным LLM-анализом.
        
        Args:
            transcriptions: Список транскрипций
            use_llm: Использовать LLM для улучшенного извлечения
        """
        facts = []
        
        # Объединяем осмысленный текст (фильтрация шума Whisper)
        full_text = self._get_meaningful_text(transcriptions)
        
        if not full_text:
            return facts
        
        # Если доступен summarizer, используем его
        if use_llm and SUMMARIZER_AVAILABLE:
            try:
                # Извлекаем задачи через few-shot
                tasks = extract_tasks(full_text)
                for task in tasks:
                    facts.append({
                        "text": task.get("task", ""),
                        "type": "task",
                        "priority": task.get("priority", "medium"),
                        "deadline": task.get("deadline"),
                        "timestamp": transcriptions[0].get("created_at") if transcriptions else None,
                    })
                
                # Анализируем эмоции
                emotions = analyze_emotions(full_text)
                if emotions.get("emotions"):
                    facts.append({
                        "text": f"Эмоции: {', '.join(emotions.get('emotions', []))}",
                        "type": "emotion",
                        "intensity": emotions.get("intensity", 0.0),
                        "timestamp": transcriptions[0].get("created_at") if transcriptions else None,
                    })
                
            except Exception as e:
                logger.warning("llm_fact_extraction_failed", error=str(e), fallback="basic")
        
        # Базовое извлечение (fallback или дополнение) — только осмысленные записи
        for trans in transcriptions:
            text = (trans.get("text") or "").strip()
            lang_prob = trans.get("language_probability") or 1.0
            if not self._is_meaningful(text, lang_prob):
                continue

            # Простое извлечение: разбиваем на предложения
            sentences = [s.strip() for s in text.split(". ") if s.strip()]

            for i, sentence in enumerate(sentences):
                if len(sentence) > 20 and self._has_cyrillic(sentence):
                    facts.append({
                        "text": sentence,
                        "type": "fact",
                        "timestamp": trans.get("created_at"),
                        "source_id": trans.get("id"),
                        "confidence": lang_prob,
                    })
        
        return facts
    
    def calculate_metrics(self, transcriptions: List[Dict], facts: List[Dict]) -> Dict:
        """
        Вычисляет метрики дня.
        
        Returns:
            Словарь с метриками
        """
        total_duration = sum(t.get("duration", 0) or 0 for t in transcriptions)
        total_chars = sum(len(t.get("text", "")) for t in transcriptions)
        total_words = sum(len(t.get("text", "").split()) for t in transcriptions)
        
        # Информационная плотность (упрощённо)
        # Высокая плотность = много фактов на единицу времени
        density_score = 0.0
        if total_duration > 0:
            facts_per_minute = (len(facts) / (total_duration / 60)) if total_duration > 0 else 0
            words_per_minute = (total_words / (total_duration / 60)) if total_duration > 0 else 0
            
            # Нормализуем (предполагаем нормальный темп ~150 слов/мин, ~5 фактов/мин)
            density_score = min(100, (facts_per_minute / 5) * 50 + (words_per_minute / 150) * 50)
        
        metrics = {
            "transcriptions_count": len(transcriptions),
            "facts_count": len(facts),
            "total_duration_minutes": round(total_duration / 60, 2) if total_duration else 0,
            "total_characters": total_chars,
            "total_words": total_words,
            "average_words_per_transcription": round(total_words / len(transcriptions), 1) if transcriptions else 0,
            "information_density_score": round(density_score, 1),
            "density_level": self._get_density_level(density_score),
        }
        
        return metrics
    
    def _get_recording_analyses_for_date(self, target_date: date) -> List[Dict]:
        """Возвращает анализы записей (recording_analyses) за день по транскрипциям."""
        if not self.db_path.exists():
            return []
        db = get_reflexio_db(self.db_path)
        try:
            rows = db.fetchall("""
                SELECT ra.id, ra.transcription_id, ra.summary, ra.emotions, ra.actions, ra.topics, ra.urgency
                FROM recording_analyses ra
                INNER JOIN transcriptions t ON ra.transcription_id = t.id
                WHERE DATE(t.created_at) = ?
                ORDER BY t.created_at ASC
            """, (target_date.isoformat(),))
            out = []
            for row in rows:
                d = dict(row)
                for key in ("emotions", "actions", "topics"):
                    if isinstance(d.get(key), str):
                        try:
                            d[key] = json.loads(d[key]) if d[key] else []
                        except (json.JSONDecodeError, TypeError):
                            d[key] = []
                out.append(d)
            return out
        except Exception as e:
            if "no such table" in str(e).lower():
                return []
            raise

    def get_daily_digest_json(self, target_date: date, user_id: Optional[str] = None) -> Dict:
        """
        Дневной итог в формате API для Android (ROADMAP Phase 2).
        Возвращает: date, summary_text, key_themes, emotions, actions, total_recordings, total_duration, repetitions.
        """
        transcriptions = self.get_transcriptions(target_date)
        analyses = self._get_recording_analyses_for_date(target_date)
        total_duration_sec = sum(t.get("duration", 0) or 0 for t in transcriptions)
        total_recordings = len(transcriptions)
        total_duration_str = f"{int(total_duration_sec // 60)}m {int(total_duration_sec % 60)}s" if total_duration_sec else "0m 0s"

        key_themes: List[str] = []
        emotions: List[str] = []
        actions: List[Dict] = []
        summary_parts: List[str] = []

        if analyses:
            for a in analyses:
                part = (a.get("summary") or "").strip()
                # ПОЧЕМУ фильтр кириллицы: старые analyses содержат галлюцинации
                # на корейском/грузинском из-за мусорных транскрипций.
                if part and self._has_cyrillic(part):
                    summary_parts.append(part)
                for t in (a.get("topics") or []):
                    if t and t not in key_themes and self._has_cyrillic(t):
                        key_themes.append(t)
                for e in (a.get("emotions") or []):
                    if e and e not in emotions:
                        emotions.append(e)
                for act in (a.get("actions") or []):
                    if isinstance(act, str) and act and self._has_cyrillic(act):
                        actions.append({"text": act, "done": False})
                    elif isinstance(act, dict) and act.get("text") and self._has_cyrillic(act["text"]):
                        actions.append({"text": act["text"], "done": act.get("done", False)})
            summary_text = " ".join(p for p in summary_parts if p).strip() or "Нет итога за день."
        else:
            facts = self.extract_facts(transcriptions)
            for f in facts:
                if f.get("type") == "task":
                    actions.append({"text": f.get("text", ""), "done": False})
                elif f.get("type") == "emotion":
                    emo_text = f.get("text", "").replace("Эмоции: ", "")
                    for e in emo_text.split(","):
                        e = e.strip()
                        if e and e not in emotions:
                            emotions.append(e)
            # ПОЧЕМУ _has_cyrillic: без этого key_themes содержит галлюцинации Whisper на всех языках
            key_themes = list(dict.fromkeys(
                f.get("text", "").split(":")[-1].strip()
                for f in facts
                if f.get("type") == "fact" and len((f.get("text") or "")) > 15
                and self._has_cyrillic(f.get("text", ""))
            ))[:15]
            full_text = self._build_tiered_digest_input(transcriptions)
            # ПОЧЕМУ CoD здесь: без LLM-суммаризации summary_text = сырой текст
            # транскрипций ("Я поеду куплю..."), а не осмысленный итог дня.
            if full_text and SUMMARIZER_AVAILABLE:
                try:
                    dense = generate_dense_summary(full_text, iterations=2)
                    validated = validate_summary(
                        dense["summary"],
                        original_text=full_text,
                        confidence_threshold=0.7,
                        auto_refine=False,
                    )
                    summary_text = validated["summary"] or full_text[:500]
                    # Извлекаем эмоции и задачи из LLM
                    try:
                        tasks = extract_tasks(full_text)
                        for task in tasks:
                            t = task.get("task", "")
                            if t and self._has_cyrillic(t):
                                actions.append({"text": t, "done": False})
                        emo = analyze_emotions(full_text)
                        for e in (emo.get("emotions") or []):
                            if e and e not in emotions:
                                emotions.append(e)
                    except Exception:
                        pass
                except Exception as e:
                    logger.warning("cod_digest_failed", error=str(e))
                    summary_text = full_text[:500] + "…" if len(full_text) > 500 else full_text or "Нет записей за день."
            else:
                summary_text = full_text[:500] + "…" if len(full_text) > 500 else full_text or "Нет записей за день."

        balance_payload = {}
        insights = []
        try:
            from src.balance.storage import get_balance_wheel
            balance_payload = get_balance_wheel(self.db_path, target_date, target_date)
        except Exception:
            balance_payload = {}

        try:
            from src.persongraph.service import save_day_psychology_snapshot, get_day_insights
            day_text = self._build_tiered_digest_input(transcriptions)
            if day_text:
                save_day_psychology_snapshot(self.db_path, target_date.isoformat(), day_text)
            insights = get_day_insights(self.db_path, target_date.isoformat())
        except Exception:
            insights = []

        return {
            "date": target_date.isoformat(),
            "summary_text": summary_text,
            "key_themes": key_themes,
            "emotions": emotions,
            "actions": actions,
            "total_recordings": total_recordings,
            "total_duration": total_duration_str,
            "repetitions": [],
            "balance": balance_payload,
            "insights": insights,
        }

    def _get_density_level(self, score: float) -> str:
        """Определяет уровень информационной плотности."""
        if score >= 80:
            return "🔴 Очень высокая"
        elif score >= 60:
            return "🟠 Высокая"
        elif score >= 40:
            return "🟡 Средняя"
        elif score >= 20:
            return "🟢 Низкая"
        else:
            return "⚪ Очень низкая"
    
    def generate_markdown(self, target_date: date, transcriptions: List[Dict], 
                         facts: List[Dict], metrics: Dict, include_metadata: bool = True) -> str:
        """
        Генерирует markdown-дайджест.
        
        Args:
            target_date: Дата
            transcriptions: Список транскрипций
            facts: Список фактов
            metrics: Метрики
            include_metadata: Включать ли метаданные
            
        Returns:
            Markdown текст
        """
        lines = []
        
        # Заголовок
        lines.append(f"# Reflexio Digest — {target_date.strftime('%d %B %Y')}")
        lines.append("")
        lines.append(f"*Сгенерировано автоматически {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*")
        lines.append("")
        
        # Метрики дня
        lines.append("## 📊 Метрики дня")
        lines.append("")
        lines.append(f"- **Транскрипций:** {metrics['transcriptions_count']}")
        lines.append(f"- **Фактов извлечено:** {metrics['facts_count']}")
        lines.append(f"- **Общая длительность:** {metrics['total_duration_minutes']} минут")
        lines.append(f"- **Слов обработано:** {metrics['total_words']}")
        lines.append(f"- **Информационная плотность:** {metrics['information_density_score']}/100 ({metrics['density_level']})")
        
        # Расширенные метрики (если есть)
        if 'extended_metrics' in metrics:
            from src.digest.metrics_ext import interpret_semantic_density, interpret_wpm_rate
            ext = metrics['extended_metrics']
            lines.append("")
            lines.append("### 🧠 Когнитивные метрики")
            lines.append("")
            
            semantic_density = ext.get('semantic_density', 0)
            wpm = ext.get('wpm_rate', 0)
            
            lines.append(f"- **Семантическая плотность:** {semantic_density:.3f}")
            lines.append(f"  *{interpret_semantic_density(semantic_density)}*")
            lines.append(f"- **Лексическое разнообразие:** {ext.get('lexical_diversity', 0):.3f}")
            lines.append(f"- **Скорость речи:** {wpm:.1f} слов/мин")
            lines.append(f"  *{interpret_wpm_rate(wpm)}*")
            lines.append(f"- **Средняя длина сегмента:** {ext.get('avg_words_per_segment', 0):.1f} слов")
            lines.append(f"- **Вариация активности:** {ext.get('hourly_variation', 0):.3f}")
            if 'segmentation' in ext:
                seg = ext['segmentation']
                lines.append(f"- **Средняя длительность сегмента:** {seg.get('avg_duration', 0):.1f} сек")
        
        lines.append("")
        
        # Информационная плотность
        lines.append("### 🎯 Анализ информационной плотности")
        lines.append("")
        
        density_desc = {
            "🔴 Очень высокая": "Очень продуктивный день с высокой концентрацией информации",
            "🟠 Высокая": "Хороший день с активным обменом информацией",
            "🟡 Средняя": "Обычный день со стандартной активностью",
            "🟢 Низкая": "Спокойный день, меньше информационного потока",
            "⚪ Очень низкая": "Минимальная активность, возможно пауза или фокус на других задачах",
        }
        
        level = metrics['density_level']
        lines.append(f"**Уровень:** {level}")
        lines.append("")
        lines.append(density_desc.get(level, "Не определён"))
        lines.append("")

        daily_payload = {}
        try:
            daily_payload = self.get_daily_digest_json(target_date)
        except Exception:
            daily_payload = {}

        balance = daily_payload.get("balance", {}) if isinstance(daily_payload, dict) else {}
        insights = daily_payload.get("insights", []) if isinstance(daily_payload, dict) else []

        if balance.get("domains"):
            lines.append("## ⚖️ Колесо Баланса")
            lines.append("")
            for domain in balance.get("domains", []):
                lines.append(
                    f"- **{domain.get('domain', 'domain')}**: {domain.get('score', 0)}/10, "
                    f"упоминаний {domain.get('mentions', 0)}, sentiment {domain.get('sentiment', 0)}"
                )
            if balance.get("alert"):
                lines.append("")
                lines.append(f"⚠️ {balance.get('alert')}")
            if balance.get("recommendation"):
                lines.append(f"💡 {balance.get('recommendation')}")
            lines.append("")

        if insights:
            lines.append("## 🧭 Инсайты")
            lines.append("")
            for insight in insights:
                role = insight.get("role", "analyst")
                text = insight.get("insight", "")
                if text:
                    lines.append(f"- **{role}:** {text}")
            lines.append("")

        # Улучшенное саммари (если доступно)
        if SUMMARIZER_AVAILABLE and transcriptions:
            try:
                full_text = self._build_tiered_digest_input(transcriptions)
                if full_text:
                    # Генерируем плотное саммари через Chain of Density
                    dense_summary = generate_dense_summary(full_text, iterations=3)
                    
                    # Валидируем через Critic
                    # ПОЧЕМУ auto_refine=False: с 0.85 порогом и эвристиками
                    # confidence почти всегда < 0.85 → лишний LLM вызов каждый раз.
                    # 0.70 соответствует get_daily_digest_json. False = не тратить токены.
                    validated = validate_summary(
                        dense_summary["summary"],
                        original_text=full_text,
                        confidence_threshold=0.70,
                        auto_refine=False,
                    )
                    
                    lines.append("## 📋 Дневное саммари")
                    lines.append("")
                    lines.append(validated["summary"])
                    lines.append("")
                    
                    if validated.get("refined"):
                        lines.append(f"*Саммари улучшено автоматически (confidence: {validated['confidence_score']:.2f})*")
                    else:
                        lines.append(f"*Confidence: {validated['confidence_score']:.2f}*")
                    lines.append("")
            except Exception as e:
                logger.warning("enhanced_summary_failed", error=str(e))
        
        # Факты
        if facts:
            lines.append("## 📝 Извлечённые факты")
            lines.append("")
            for i, fact in enumerate(facts, 1):
                timestamp = fact.get("timestamp", "")[:16] if fact.get("timestamp") else ""
                fact_type = fact.get("type", "fact")
                lines.append(f"### {i}. [{fact_type.upper()}] {fact['text']}")
                if include_metadata and timestamp:
                    lines.append(f"*{timestamp}*")
                if fact_type == "task" and fact.get("priority"):
                    lines.append(f"*Приоритет: {fact['priority']}*")
                lines.append("")
        else:
            lines.append("## 📝 Факты")
            lines.append("")
            lines.append("*Факты не найдены*")
            lines.append("")
        
        # Транскрипции (если включены)
        if include_metadata and transcriptions:
            lines.append("## 🎤 Полные транскрипции")
            lines.append("")
            for i, trans in enumerate(transcriptions, 1):
                timestamp = trans.get("created_at", "")[:16] if trans.get("created_at") else ""
                language = trans.get("language", "unknown")
                duration = trans.get("duration", 0) or 0
                
                lines.append(f"### Транскрипция #{i}")
                lines.append(f"*{timestamp} | {language} | {duration:.1f}s*")
                lines.append("")
                lines.append(f"> {trans.get('text', '')}")
                lines.append("")
        
        # Подвал
        lines.append("---")
        lines.append("")
        lines.append("*Reflexio 24/7 — автоматический дневной дайджест*")
        
        return "\n".join(lines)
    
    def generate_json(self, target_date: date, transcriptions: List[Dict],
                     facts: List[Dict], metrics: Dict) -> Dict:
        """
        Генерирует JSON-дайджест с CoVe валидацией.
        
        Returns:
            Валидированный JSON-дайджест
        """
        digest_dict = {
            "date": target_date.isoformat(),
            "generated_at": datetime.now().isoformat(),
            "metrics": metrics,
            "facts": facts,
            "transcriptions": transcriptions if transcriptions else [],
        }
        
        # ПОЧЕМУ убрали CoVe importlib: аналогично H5 safe_middleware —
        # exec_module() произвольного .py файла из .cursor/ = RCE вектор.
        return digest_dict
    
    def generate(self, target_date: date, output_format: str = "markdown",
                include_metadata: bool = True, generate_pdf: bool = False) -> Path:
        """
        Генерирует дайджест для указанной даты.
        
        Args:
            target_date: Дата
            output_format: Формат ("markdown" или "json")
            include_metadata: Включать ли метаданные
            
        Returns:
            Путь к созданному файлу
        """
        logger.info("generating_digest", date=target_date.isoformat(), format=output_format)
        
        # Получаем транскрипции
        transcriptions = self.get_transcriptions(target_date)
        
        if not transcriptions:
            logger.warning("no_transcriptions", date=target_date.isoformat())
            # Создаём пустой дайджест
            metrics = {
                "transcriptions_count": 0,
                "facts_count": 0,
                "total_duration_minutes": 0,
                "total_characters": 0,
                "total_words": 0,
                "average_words_per_transcription": 0,
                "information_density_score": 0.0,
                "density_level": "⚪ Очень низкая",
            }
            facts = []
        else:
            # Извлекаем факты
            facts = self.extract_facts(transcriptions)
            
        # Вычисляем базовые метрики
        metrics = self.calculate_metrics(transcriptions, facts)
        
        # Добавляем расширенные метрики (если включено)
        extended_enabled = getattr(settings, "EXTENDED_METRICS", False)
        if extended_enabled:
            # Получаем распределение по часам для расширенных метрик
            hourly_dist = {}
            for trans in transcriptions:
                if trans.get("created_at"):
                    try:
                        hour = datetime.fromisoformat(trans["created_at"]).strftime("%H")
                        hourly_dist[hour] = hourly_dist.get(hour, 0) + 1
                    except Exception:
                        pass
            
            extended = calculate_extended_metrics(
                transcriptions=transcriptions,
                hourly_distribution=hourly_dist,
                enabled=True,
            )
            if extended:
                metrics["extended_metrics"] = extended
        
        # Генерируем дайджест
        if output_format == "pdf" or generate_pdf:
            try:
                from src.digest.pdf_generator import PDFGenerator
                pdf_gen = PDFGenerator()
                output_file = pdf_gen.generate(
                    target_date=target_date,
                    transcriptions=transcriptions,
                    facts=facts,
                    metrics=metrics,
                )
                logger.info(
                    "digest_pdf_generated",
                    date=target_date.isoformat(),
                    file=str(output_file),
                )
                return output_file
            except ImportError:
                logger.warning("pdf_generation_failed", reason="reportlab_not_available", fallback="markdown")
                # Fallback на markdown
                output_format = "markdown"
        
        if output_format == "json":
            content = json.dumps(self.generate_json(target_date, transcriptions, facts, metrics), 
                               indent=2, ensure_ascii=False)
            ext = "json"
        else:
            content = self.generate_markdown(target_date, transcriptions, facts, metrics, include_metadata)
            ext = "md"
        
        # Сохраняем
        output_file = self.digests_dir / f"digest_{target_date.isoformat()}.{ext}"
        output_file.write_text(content, encoding="utf-8")
        
        logger.info(
            "digest_generated",
            date=target_date.isoformat(),
            file=str(output_file),
            facts=len(facts),
            transcriptions=len(transcriptions),
            density=metrics.get("information_density_score", 0),
        )
        
        # Синхронизируем память с дайджестом (инсайты и паттерны)
        try:
            core_memory = get_core_memory()
            session_memory = get_session_memory()
            
            # Создаём сессию для дня
            session_id = f"day_{target_date.isoformat()}"
            session_memory.create_session(session_id, metadata={
                "date": target_date.isoformat(),
                "transcriptions_count": len(transcriptions),
                "facts_count": len(facts),
                "density_score": metrics.get("information_density_score", 0),
            })
            
            # Добавляем контексты из фактов
            for fact in facts[:20]:  # Ограничиваем количество
                session_memory.add_context(session_id, {
                    "type": fact.get("type", "fact"),
                    "text": fact.get("text", ""),
                    "timestamp": fact.get("timestamp"),
                })
            
            # Обновляем core memory с паттернами
            if facts:
                # Анализируем паттерны (например, частота типов фактов)
                fact_types = {}
                for fact in facts:
                    fact_type = fact.get("type", "fact")
                    fact_types[fact_type] = fact_types.get(fact_type, 0) + 1
                
                # Сохраняем паттерны дня
                daily_patterns = core_memory.get("daily_patterns", {})
                daily_patterns[target_date.isoformat()] = {
                    "fact_types": fact_types,
                    "density_score": metrics.get("information_density_score", 0),
                }
                # Ограничиваем историю (последние 30 дней)
                if len(daily_patterns) > 30:
                    oldest_date = min(daily_patterns.keys())
                    del daily_patterns[oldest_date]
                core_memory.set("daily_patterns", daily_patterns)
            
            logger.info("memory_synced_with_digest", date=target_date.isoformat())
            
        except Exception as e:
            logger.warning("memory_sync_failed", error=str(e), continue_without_sync=True)
        
        return output_file
















