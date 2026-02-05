"""Генератор дайджестов из транскриптов с улучшенным summarization."""
import sqlite3
from datetime import date, datetime
from pathlib import Path
from typing import Optional, Dict, List
import json

from src.utils.config import settings
from src.utils.logging import setup_logging, get_logger
from src.digest.metrics_ext import calculate_extended_metrics
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
    
    def __init__(self, db_path: Optional[Path] = None):
        """Инициализация генератора."""
        if db_path is None:
            db_path = settings.STORAGE_PATH / "reflexio.db"
        self.db_path = db_path
        self.digests_dir = Path("digests")
        self.digests_dir.mkdir(parents=True, exist_ok=True)
    
    def get_transcriptions(self, target_date: date) -> List[Dict]:
        """
        Получает все транскрипции за день.
        
        Args:
            target_date: Дата для выборки
            
        Returns:
            Список транскрипций с метаданными
        """
        if not self.db_path.exists():
            logger.warning("database_not_found", db_path=str(self.db_path))
            return []
        
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        
        try:
            cursor = conn.cursor()
            
            # Получаем транскрипции за день
            cursor.execute("""
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
                WHERE DATE(t.created_at) = ?
                ORDER BY t.created_at ASC
            """, (target_date.isoformat(),))
            
            rows = cursor.fetchall()
            transcriptions = [dict(row) for row in rows]
            
            logger.info(
                "transcriptions_found",
                date=target_date.isoformat(),
                count=len(transcriptions),
            )
            
            return transcriptions
            
        finally:
            conn.close()
    
    def extract_facts(self, transcriptions: List[Dict], use_llm: bool = True) -> List[Dict]:
        """
        Извлекает факты из транскрипций с улучшенным LLM-анализом.
        
        Args:
            transcriptions: Список транскрипций
            use_llm: Использовать LLM для улучшенного извлечения
        """
        facts = []
        
        # Объединяем весь текст для анализа
        full_text = " ".join([t.get("text", "").strip() for t in transcriptions if t.get("text", "").strip()])
        
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
        
        # Базовое извлечение (fallback или дополнение)
        for trans in transcriptions:
            text = trans.get("text", "").strip()
            if not text:
                continue
            
            # Простое извлечение: разбиваем на предложения
            sentences = [s.strip() for s in text.split(". ") if s.strip()]
            
            for i, sentence in enumerate(sentences):
                if len(sentence) > 20:  # Минимальная длина факта
                    facts.append({
                        "text": sentence,
                        "type": "fact",
                        "timestamp": trans.get("created_at"),
                        "source_id": trans.get("id"),
                        "confidence": trans.get("language_probability", 0.0),
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
        
        # Улучшенное саммари (если доступно)
        if SUMMARIZER_AVAILABLE and transcriptions:
            try:
                full_text = " ".join([t.get("text", "").strip() for t in transcriptions if t.get("text", "").strip()])
                if full_text:
                    # Генерируем плотное саммари через Chain of Density
                    dense_summary = generate_dense_summary(full_text, iterations=3)
                    
                    # Валидируем через Critic
                    validated = validate_summary(
                        dense_summary["summary"],
                        original_text=full_text,
                        confidence_threshold=0.85,
                        auto_refine=True,
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
        
        # CoVe валидация дайджеста
        try:
            import sys
            import importlib.util
            from pathlib import Path as PathLib
            cove_path = PathLib(__file__).parent.parent.parent / ".cursor" / "validation" / "cove" / "verify.py"
            if cove_path.exists():
                spec = importlib.util.spec_from_file_location("cove_verify", cove_path)
                cove_module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(cove_module)
                cove = cove_module.CoVeVerifier()
                
                # Проверяем схему дайджеста
                schema_valid, schema_errors = cove.verify_schema(digest_dict, "digest")
                if not schema_valid:
                    logger.warning("cove_digest_schema_validation_failed", errors=schema_errors)
                else:
                    logger.debug("cove_digest_validation_passed")
                
                # Проверяем timestamps
                ts_valid, ts_errors = cove.verify_timestamps(digest_dict, ["generated_at"])
                if not ts_valid:
                    logger.warning("cove_digest_timestamps_validation_failed", errors=ts_errors)
        except Exception as e:
            logger.debug("cove_digest_validation_skipped", error=str(e))
        
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
                    except:
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

