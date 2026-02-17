"""
Embeddings для semantic search в аудио с кэшированием.
Reflexio v2.1 — Surpass Smart Noter Sprint
"""
from typing import List, Dict, Any, Optional
from pathlib import Path
import os
import hashlib
import json

from src.utils.logging import get_logger

logger = get_logger("storage.embeddings")

# Кэш для embeddings (в памяти)
_embeddings_cache: Dict[str, List[float]] = {}
_cache_file = Path(".cache/embeddings_cache.json")


def _load_cache():
    """Загружает кэш из файла."""
    global _embeddings_cache
    if _cache_file.exists():
        try:
            with open(_cache_file, "r", encoding="utf-8") as f:
                _embeddings_cache = json.load(f)
            logger.info("embeddings_cache_loaded", entries=len(_embeddings_cache))
        except Exception as e:
            logger.warning("embeddings_cache_load_failed", error=str(e))


def _save_cache():
    """Сохраняет кэш в файл."""
    try:
        _cache_file.parent.mkdir(parents=True, exist_ok=True)
        with open(_cache_file, "w", encoding="utf-8") as f:
            json.dump(_embeddings_cache, f)
        logger.debug("embeddings_cache_saved", entries=len(_embeddings_cache))
    except Exception as e:
        logger.warning("embeddings_cache_save_failed", error=str(e))


def _get_cache_key(text: str, model: str) -> str:
    """Генерирует ключ кэша для текста и модели."""
    key_string = f"{model}:{text}"
    return hashlib.md5(key_string.encode("utf-8")).hexdigest()


# Загружаем кэш при импорте
_load_cache()


def generate_embeddings(text: str, model: str = "text-embedding-3-small", use_cache: bool = True) -> List[float]:
    """
    Генерирует embeddings для текста с кэшированием.
    
    Args:
        text: Текст для embedding
        model: Модель для embeddings (OpenAI или локальная)
        use_cache: Использовать ли кэш
        
    Returns:
        Список чисел (вектор embedding)
    """
    # Проверяем кэш
    if use_cache:
        cache_key = _get_cache_key(text, model)
        if cache_key in _embeddings_cache:
            logger.debug("embeddings_cache_hit", cache_key=cache_key[:8])
            return _embeddings_cache[cache_key]
    
    # Генерируем embedding
    embedding = None
    
    # Пробуем OpenAI embeddings
    try:
        import openai
        api_key = os.getenv("OPENAI_API_KEY")
        if api_key:
            client = openai.OpenAI(api_key=api_key)
            response = client.embeddings.create(
                model=model,
                input=text,
            )
            embedding = response.data[0].embedding
            logger.debug("embeddings_generated_openai", model=model)
    except Exception as e:
        logger.warning("openai_embeddings_failed", error=str(e))
    
    # Fallback на локальную модель (если доступна)
    if embedding is None:
        try:
            from sentence_transformers import SentenceTransformer
            model_st = SentenceTransformer('all-MiniLM-L6-v2')
            embedding = model_st.encode(text).tolist()
            logger.debug("embeddings_generated_local", model="all-MiniLM-L6-v2")
        except ImportError:
            logger.warning("sentence_transformers_not_available")
    
    # Если ничего не работает, возвращаем пустой вектор
    if embedding is None:
        logger.error("embeddings_generation_failed", fallback="empty_vector")
        embedding = [0.0] * 384  # Размер по умолчанию
    
    # Сохраняем в кэш
    if use_cache:
        cache_key = _get_cache_key(text, model)
        _embeddings_cache[cache_key] = embedding
        # Сохраняем кэш периодически (каждые 100 новых записей)
        if len(_embeddings_cache) % 100 == 0:
            _save_cache()
    
    return embedding


def store_embeddings(
    audio_id: str,
    segments: List[Dict[str, Any]],
    db_backend: Any = None,
) -> bool:
    """
    Сохраняет embeddings для сегментов аудио.
    
    Args:
        audio_id: ID аудио файла
        segments: Список сегментов с текстом и timestamps
        db_backend: Бэкенд БД (если None, используется get_db)
        
    Returns:
        True если успешно
    """
    try:
        if db_backend is None:
            from src.storage.db import get_db
            db_backend = get_db()
        
        for segment in segments:
            text = segment.get("text", "")
            start_time = segment.get("start", 0.0)
            
            if not text:
                continue
            
            # Генерируем embedding
            embedding = generate_embeddings(text)
            
            # Сохраняем в БД (предполагаем таблицу text_entries с полем embedding)
            entry_data = {
                "mission_id": audio_id,
                "content": text,
                "embedding": embedding,  # Для pgvector
                "metadata": {
                    "start_time": start_time,
                    "end_time": segment.get("end", start_time),
                    "confidence": segment.get("confidence", 0.0),
                },
            }
            
            db_backend.insert("text_entries", entry_data)
        
        logger.info("embeddings_stored", audio_id=audio_id, segments_count=len(segments))
        return True
        
    except Exception as e:
        logger.error("embeddings_storage_failed", error=str(e))
        return False


def search_phrases(
    query: str,
    audio_id: Optional[str] = None,
    limit: int = 10,
    db_backend: Any = None,
) -> List[Dict[str, Any]]:
    """
    Ищет фразы по semantic similarity.
    
    Args:
        query: Поисковый запрос
        audio_id: ID аудио (если None, ищет во всех)
        limit: Максимальное количество результатов
        
    Returns:
        Список совпадений с текстом, timestamp и confidence
    """
    try:
        if db_backend is None:
            from src.storage.db import get_db
            db_backend = get_db()
        
        # Генерируем embedding для запроса (для pgvector — пока не используется)
        generate_embeddings(query)
        
        # Поиск через pgvector (если доступен)
        # Иначе используем простой поиск по тексту
        if audio_id:
            filters = {"mission_id": audio_id}
        else:
            filters = None
        
        # Простой поиск (можно улучшить через pgvector similarity)
        entries = db_backend.select("text_entries", filters=filters, limit=limit * 2)
        
        # Сортируем по similarity (упрощённая версия)
        results = []
        for entry in entries:
            entry_text = entry.get("content", "")
            if query.lower() in entry_text.lower():
                results.append({
                    "text": entry_text,
                    "start": entry.get("metadata", {}).get("start_time", 0.0),
                    "end": entry.get("metadata", {}).get("end_time", 0.0),
                    "confidence": entry.get("metadata", {}).get("confidence", 0.0),
                })
        
        return results[:limit]
        
    except Exception as e:
        logger.error("phrase_search_failed", error=str(e))
        return []

