"""Анализатор информационной плотности и паттернов."""
from datetime import date
from typing import Dict
import sqlite3
from pathlib import Path

from src.utils.config import settings
from src.utils.logging import setup_logging, get_logger
from src.digest.metrics_ext import calculate_extended_metrics, interpret_semantic_density, interpret_wpm_rate

setup_logging()
logger = get_logger("digest.analyzer")


class InformationDensityAnalyzer:
    """Анализирует информационную плотность дня."""
    
    def __init__(self, db_path: Path | None = None):
        """Инициализация анализатора."""
        if db_path is None:
            db_path = settings.STORAGE_PATH / "reflexio.db"
        self.db_path = db_path
    
    def analyze_day(self, target_date: date) -> Dict:
        """
        Анализирует информационную плотность дня.
        
        Args:
            target_date: Дата для анализа
            
        Returns:
            Словарь с результатами анализа
        """
        if not self.db_path.exists():
            logger.warning("database_not_found", db_path=str(self.db_path))
            return self._empty_analysis(target_date)
        
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        
        try:
            cursor = conn.cursor()
            
            # Получаем статистику транскрипций
            cursor.execute("""
                SELECT 
                    COUNT(*) as count,
                    SUM(duration) as total_duration,
                    SUM(LENGTH(text)) as total_chars,
                    AVG(LENGTH(text)) as avg_chars
                FROM transcriptions
                WHERE DATE(created_at) = ?
            """, (target_date.isoformat(),))
            
            stats = dict(cursor.fetchone() or {})
            
            # Распределение по часам
            cursor.execute("""
                SELECT 
                    strftime('%H', created_at) as hour,
                    COUNT(*) as count
                FROM transcriptions
                WHERE DATE(created_at) = ?
                GROUP BY hour
                ORDER BY hour
            """, (target_date.isoformat(),))
            
            hourly_distribution = {row[0]: row[1] for row in cursor.fetchall()}
            
            # Вычисляем плотность
            total_duration = stats.get("total_duration") or 0
            total_chars = stats.get("total_chars") or 0
            count = stats.get("count") or 0
            
            density_metrics = self._calculate_density_metrics(
                count, total_duration, total_chars, hourly_distribution
            )
            
            # Получаем полные транскрипции для расширенных метрик
            transcriptions = []
            if count > 0:
                cursor.execute("""
                    SELECT 
                        id,
                        text,
                        duration,
                        created_at
                    FROM transcriptions
                    WHERE DATE(created_at) = ?
                    ORDER BY created_at ASC
                """, (target_date.isoformat(),))
                transcriptions = [dict(row) for row in cursor.fetchall()]
            
            # Вычисляем расширенные метрики (если включено)
            extended_metrics = calculate_extended_metrics(
                transcriptions=transcriptions,
                hourly_distribution=hourly_distribution,
                enabled=getattr(settings, "EXTENDED_METRICS", False),
            )
            
            # Объединяем базовые и расширенные метрики
            result = {
                "date": target_date.isoformat(),
                "statistics": {
                    "transcriptions_count": count,
                    "total_duration_seconds": total_duration,
                    "total_duration_minutes": round(total_duration / 60, 2) if total_duration else 0,
                    "total_characters": total_chars,
                    "average_characters_per_transcription": round(stats.get("avg_chars") or 0, 1),
                },
                "hourly_distribution": hourly_distribution,
                "density_analysis": density_metrics,
            }
            
            # Добавляем расширенные метрики если они есть
            if extended_metrics:
                result["extended_metrics"] = extended_metrics
                result["extended_metrics"]["interpretation"] = {
                    "semantic_density": interpret_semantic_density(extended_metrics.get("semantic_density", 0)),
                    "wpm_rate": interpret_wpm_rate(extended_metrics.get("wpm_rate", 0)),
                }
            
            logger.info(
                "density_analysis_complete",
                date=target_date.isoformat(),
                density_score=density_metrics.get("score", 0),
            )
            
            return result
            
        finally:
            conn.close()
    
    def _calculate_density_metrics(self, count: int, total_duration: float,
                                   total_chars: int, hourly_distribution: Dict[str, int]) -> Dict:
        """Вычисляет метрики информационной плотности."""
        
        # Базовая плотность по времени
        time_density = 0.0
        if total_duration > 0:
            # Транскрипций в минуту
            trans_per_minute = (count / (total_duration / 60)) if total_duration > 0 else 0
            # Нормализуем (предполагаем нормальный темп ~2 транскрипции/мин)
            time_density = min(50, (trans_per_minute / 2) * 50)
        
        # Плотность по объёму
        volume_density = 0.0
        if count > 0:
            avg_chars = total_chars / count
            # Нормализуем (предполагаем нормальную длину ~200 символов)
            volume_density = min(50, (avg_chars / 200) * 50)
        
        # Равномерность распределения (меньше пиков = выше равномерность)
        distribution_score = 0.0
        if hourly_distribution:
            hours_with_activity = len(hourly_distribution)
            max_in_hour = max(hourly_distribution.values())
            if max_in_hour > 0:
                # Равномерность = как много часов относительно пика
                distribution_score = min(50, (hours_with_activity / max_in_hour) * 25)
        
        # Общая оценка
        total_score = time_density * 0.4 + volume_density * 0.4 + distribution_score * 0.2
        
        # Определяем уровень
        level = self._get_density_level(total_score)
        
        return {
            "score": round(total_score, 1),
            "level": level,
            "components": {
                "time_density": round(time_density, 1),
                "volume_density": round(volume_density, 1),
                "distribution_score": round(distribution_score, 1),
            },
            "interpretation": self._interpret_density(total_score, count, total_duration),
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
    
    def _interpret_density(self, score: float, count: int, duration: float) -> str:
        """Интерпретирует результат анализа."""
        if score >= 80:
            return "Очень продуктивный день с высокой информационной активностью"
        elif score >= 60:
            return "Хороший день с активным обменом информацией"
        elif score >= 40:
            return "Обычный день со стандартной активностью"
        elif score >= 20:
            return "Спокойный день, меньше информационного потока"
        elif count > 0:
            return "Минимальная активность, возможно пауза или фокус на других задачах"
        else:
            return "Нет активности за этот день"
    
    def _empty_analysis(self, target_date: date) -> Dict:
        """Возвращает пустой анализ."""
        return {
            "date": target_date.isoformat(),
            "statistics": {
                "transcriptions_count": 0,
                "total_duration_seconds": 0,
                "total_duration_minutes": 0,
                "total_characters": 0,
                "average_characters_per_transcription": 0,
            },
            "hourly_distribution": {},
            "density_analysis": {
                "score": 0.0,
                "level": "⚪ Очень низкая",
                "components": {
                    "time_density": 0.0,
                    "volume_density": 0.0,
                    "distribution_score": 0.0,
                },
                "interpretation": "Нет данных за этот день",
            },
        }

