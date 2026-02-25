"""
Embeddings для semantic search в аудио с кэшированием.
Reflexio v2.1 — lightweight-safe runtime by default.
"""
from typing import List, Dict, Any, Optional
from pathlib import Path
import hashlib
import json
import os

from src.utils.logging import get_logger

logger = get_logger("storage.embeddings")

_embeddings_cache: Dict[str, List[float]] = {}
_cache_file = Path(".cache/embeddings_cache.json")


def _load_cache() -> None:
    global _embeddings_cache
    if _cache_file.exists():
        try:
            with open(_cache_file, "r", encoding="utf-8") as f:
                _embeddings_cache = json.load(f)
        except Exception as e:
            logger.warning("embeddings_cache_load_failed", error=str(e))


def _save_cache() -> None:
    try:
        _cache_file.parent.mkdir(parents=True, exist_ok=True)
        with open(_cache_file, "w", encoding="utf-8") as f:
            json.dump(_embeddings_cache, f)
    except Exception as e:
        logger.warning("embeddings_cache_save_failed", error=str(e))


def _get_cache_key(text: str, model: str) -> str:
    # ПОЧЕМУ usedforsecurity=False: MD5 здесь только как cache key (быстрый хэш),
    # не для криптографической защиты. SHA-256 используется для integrity chain.
    return hashlib.md5(f"{model}:{text}".encode("utf-8"), usedforsecurity=False).hexdigest()  # nosec B324


def _hash_fallback_embedding(text: str, dim: int = 384) -> List[float]:
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    base = list(digest)
    return [float(base[i % len(base)]) / 255.0 for i in range(dim)]


_load_cache()


def generate_embeddings(text: str, model: str = "text-embedding-3-small", use_cache: bool = True) -> List[float]:
    """Генерирует embeddings для текста с безопасным fallback."""
    if use_cache:
        cache_key = _get_cache_key(text, model)
        if cache_key in _embeddings_cache:
            return _embeddings_cache[cache_key]

    embedding: List[float] | None = None

    # OpenAI embedding path (optional).
    try:
        api_key = os.getenv("OPENAI_API_KEY")
        if api_key:
            import openai

            client = openai.OpenAI(api_key=api_key)
            response = client.embeddings.create(model=model, input=text)
            embedding = response.data[0].embedding
    except Exception as e:
        logger.warning("openai_embeddings_failed", error=str(e))

    # Optional heavy local model only by explicit flag.
    if embedding is None and os.getenv("ENABLE_LOCAL_EMBEDDINGS", "false").lower() == "true":
        try:
            from sentence_transformers import SentenceTransformer

            model_st = SentenceTransformer("all-MiniLM-L6-v2")
            embedding = model_st.encode(text).tolist()
        except Exception as e:
            logger.warning("sentence_transformers_unavailable", error=str(e))

    # Deterministic zero-dependency fallback.
    if embedding is None:
        embedding = _hash_fallback_embedding(text)

    if use_cache:
        cache_key = _get_cache_key(text, model)
        _embeddings_cache[cache_key] = embedding
        if len(_embeddings_cache) % 100 == 0:
            _save_cache()

    return embedding


def store_embeddings(audio_id: str, segments: List[Dict[str, Any]], db_backend: Any = None) -> bool:
    """Сохраняет embeddings для сегментов аудио."""
    try:
        if db_backend is None:
            from src.storage.db import get_db

            db_backend = get_db()

        for segment in segments:
            text = segment.get("text", "")
            if not text:
                continue

            entry_data = {
                "mission_id": audio_id,
                "content": text,
                "embedding": generate_embeddings(text),
                "metadata": {
                    "start_time": segment.get("start", 0.0),
                    "end_time": segment.get("end", segment.get("start", 0.0)),
                    "confidence": segment.get("confidence", 0.0),
                },
            }
            db_backend.insert("text_entries", entry_data)

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
    """Ищет фразы по semantic/lexical match (упрощённо)."""
    try:
        if db_backend is None:
            from src.storage.db import get_db

            db_backend = get_db()

        generate_embeddings(query)

        filters = {"mission_id": audio_id} if audio_id else None
        entries = db_backend.select("text_entries", filters=filters, limit=limit * 2)

        results = []
        for entry in entries:
            entry_text = entry.get("content", "")
            if query.lower() in entry_text.lower():
                results.append(
                    {
                        "text": entry_text,
                        "start": entry.get("metadata", {}).get("start_time", 0.0),
                        "end": entry.get("metadata", {}).get("end_time", 0.0),
                        "confidence": entry.get("metadata", {}).get("confidence", 0.0),
                    }
                )

        return results[:limit]
    except Exception as e:
        logger.error("phrase_search_failed", error=str(e))
        return []

