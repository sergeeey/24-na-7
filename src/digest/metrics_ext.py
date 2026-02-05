"""Расширенные метрики для когнитивного анализа речи."""
from collections import Counter
from typing import List, Dict, Optional
import numpy as np

from src.utils.logging import setup_logging, get_logger

setup_logging()
logger = get_logger("digest.metrics_ext")


def lexical_diversity(texts: List[str]) -> float:
    """
    Вычисляет лексическое разнообразие (type-token ratio).
    
    Мера того, насколько разнообразен словарный запас.
    Значение от 0 до 1, где 1 = все слова уникальны.
    
    Args:
        texts: Список текстов
        
    Returns:
        Лексическое разнообразие (0-1)
    """
    if not texts:
        return 0.0
    
    # Объединяем все тексты и разбиваем на слова
    all_text = " ".join(texts).lower()
    words = [w.strip(".,!?;:()[]{}'\"") for w in all_text.split() if w.strip()]
    
    if not words:
        return 0.0
    
    unique_words = len(set(words))
    total_words = len(words)
    
    diversity = unique_words / (total_words + 1e-6)
    
    return float(diversity)


def avg_words_per_segment(texts: List[str]) -> float:
    """
    Среднее количество слов на сегмент.
    
    Args:
        texts: Список текстов
        
    Returns:
        Среднее количество слов
    """
    if not texts:
        return 0.0
    
    word_counts = [len(text.split()) for text in texts if text.strip()]
    
    if not word_counts:
        return 0.0
    
    return float(np.mean(word_counts))


def avg_chars_per_segment(texts: List[str]) -> float:
    """
    Среднее количество символов на сегмент.
    
    Args:
        texts: Список текстов
        
    Returns:
        Среднее количество символов
    """
    if not texts:
        return 0.0
    
    char_counts = [len(text) for text in texts if text.strip()]
    
    if not char_counts:
        return 0.0
    
    return float(np.mean(char_counts))


def hourly_density_variation(density_by_hour: List[float]) -> float:
    """
    Вычисляет вариацию плотности по часам (стандартное отклонение).
    
    Показывает, насколько равномерно распределена активность.
    Низкое значение = равномерная активность, высокое = пиковая активность.
    
    Args:
        density_by_hour: Список значений плотности по часам (0-23)
        
    Returns:
        Стандартное отклонение
    """
    if not density_by_hour:
        return 0.0
    
    # Нормализуем для лучшей интерпретации
    values = np.array(density_by_hour)
    if np.sum(values) == 0:
        return 0.0
    
    # Стандартное отклонение
    std_dev = float(np.std(values))
    
    return std_dev


def wpm_rate(segment_durations: List[float], segment_texts: List[str]) -> float:
    """
    Вычисляет среднюю скорость речи (words per minute).
    
    Args:
        segment_durations: Длительность сегментов в секундах
        segment_texts: Тексты сегментов
        
    Returns:
        Средняя скорость речи (слов/минуту)
    """
    if not segment_durations or not segment_texts:
        return 0.0
    
    rates = []
    for duration, text in zip(segment_durations, segment_texts):
        if duration > 0 and text.strip():
            words = len(text.split())
            wpm = (words / duration) * 60
            rates.append(wpm)
    
    if not rates:
        return 0.0
    
    return float(np.mean(rates))


def semantic_density_score(
    texts: List[str],
    diversity_weight: float = 0.4,
    length_weight: float = 0.3,
    word_density_weight: float = 0.3,
) -> float:
    """
    Интегральная оценка семантической плотности текстов.
    
    Комбинирует несколько метрик в единую оценку (0-1):
    - Лексическое разнообразие
    - Средняя длина сегментов
    - Плотность слов (слова на символ)
    
    Args:
        texts: Список текстов
        diversity_weight: Вес лексического разнообразия
        length_weight: Вес средней длины
        word_density_weight: Вес плотности слов
        
    Returns:
        Оценка семантической плотности (0-1)
    """
    if not texts:
        return 0.0
    
    # Лексическое разнообразие
    diversity = lexical_diversity(texts)
    
    # Средняя длина сегментов (нормализуем: предполагаем норма ~50 слов)
    avg_words = avg_words_per_segment(texts)
    length_score = min(1.0, avg_words / 50.0)
    
    # Плотность слов (слов на символ, нормализуем)
    all_chars = sum(len(t) for t in texts)
    all_words = sum(len(t.split()) for t in texts)
    word_density = (all_words / (all_chars + 1e-6)) * 10  # Умножаем на 10 для нормализации
    word_density_score = min(1.0, word_density)
    
    # Комбинируем
    score = (
        diversity_weight * diversity +
        length_weight * length_score +
        word_density_weight * word_density_score
    )
    
    return float(score)


def calculate_segmentation_metrics(segments: List[Dict]) -> Dict:
    """
    Вычисляет метрики сегментации.
    
    Args:
        segments: Список сегментов с полями 'text', 'duration', 'timestamp'
        
    Returns:
        Словарь с метриками сегментации
    """
    if not segments:
        return {
            "avg_duration": 0.0,
            "avg_words_per_segment": 0.0,
            "total_segments": 0,
            "total_words": 0,
        }
    
    texts = [s.get("text", "") for s in segments]
    durations = [s.get("duration", 0) or 0 for s in segments]
    
    return {
        "avg_duration": float(np.mean(durations)) if durations else 0.0,
        "avg_words_per_segment": avg_words_per_segment(texts),
        "total_segments": len(segments),
        "total_words": sum(len(t.split()) for t in texts),
    }


def calculate_extended_metrics(
    transcriptions: List[Dict],
    hourly_distribution: Optional[Dict[str, int]] = None,
    enabled: bool = True,
) -> Dict:
    """
    Вычисляет расширенные метрики для когнитивного анализа.
    
    Args:
        transcriptions: Список транскрипций с полями 'text', 'duration', 'created_at'
        hourly_distribution: Распределение транскрипций по часам
        enabled: Включены ли расширенные метрики
        
    Returns:
        Словарь с расширенными метриками
    """
    if not enabled:
        return {}
    
    if not transcriptions:
        return {
            "lexical_diversity": 0.0,
            "semantic_density": 0.0,
            "avg_words_per_segment": 0.0,
            "avg_chars_per_segment": 0.0,
            "wpm_rate": 0.0,
            "hourly_variation": 0.0,
            "segmentation": {},
        }
    
    # Извлекаем данные
    texts = [t.get("text", "") for t in transcriptions if t.get("text", "").strip()]
    durations = [t.get("duration", 0) or 0 for t in transcriptions]
    
    if not texts:
        return {
            "lexical_diversity": 0.0,
            "semantic_density": 0.0,
            "avg_words_per_segment": 0.0,
            "avg_chars_per_segment": 0.0,
            "wpm_rate": 0.0,
            "hourly_variation": 0.0,
            "segmentation": {},
        }
    
    # Базовые метрики
    diversity = lexical_diversity(texts)
    avg_words = avg_words_per_segment(texts)
    avg_chars = avg_chars_per_segment(texts)
    semantic_density = semantic_density_score(texts)
    wpm = wpm_rate(durations, texts)
    
    # Метрики сегментации
    segmentation = calculate_segmentation_metrics([
        {
            "text": t.get("text", ""),
            "duration": t.get("duration", 0) or 0,
            "timestamp": t.get("created_at", ""),
        }
        for t in transcriptions
    ])
    
    # Вариация по часам
    hourly_var = 0.0
    if hourly_distribution:
        # Создаём массив плотности по часам (0-23)
        hours = [int(h) for h in hourly_distribution.keys() if h.isdigit()]
        if hours:
            max_hour = max(hours) if hours else 23
            density_array = [hourly_distribution.get(str(h), 0) for h in range(max_hour + 1)]
            hourly_var = hourly_density_variation(density_array)
    
    return {
        "lexical_diversity": round(diversity, 3),
        "semantic_density": round(semantic_density, 3),
        "avg_words_per_segment": round(avg_words, 1),
        "avg_chars_per_segment": round(avg_chars, 1),
        "wpm_rate": round(wpm, 1),
        "hourly_variation": round(hourly_var, 3),
        "segmentation": segmentation,
    }


def interpret_semantic_density(score: float) -> str:
    """
    Интерпретирует оценку семантической плотности.
    
    Args:
        score: Оценка семантической плотности (0-1)
        
    Returns:
        Текстовое описание
    """
    if score >= 0.7:
        return "🔴 Очень высокая — очень насыщенная речь с богатым словарём"
    elif score >= 0.5:
        return "🟠 Высокая — содержательная речь"
    elif score >= 0.3:
        return "🟡 Средняя — стандартная речь"
    elif score >= 0.15:
        return "🟢 Низкая — простая, повторяющаяся речь"
    else:
        return "⚪ Очень низкая — минимальное содержание"


def interpret_wpm_rate(wpm: float) -> str:
    """
    Интерпретирует скорость речи.
    
    Args:
        wpm: Скорость речи (слов/минуту)
        
    Returns:
        Текстовое описание
    """
    if wpm >= 180:
        return "Очень быстрая"
    elif wpm >= 150:
        return "Быстрая"
    elif wpm >= 120:
        return "Средняя"
    elif wpm >= 90:
        return "Медленная"
    else:
        return "Очень медленная"













