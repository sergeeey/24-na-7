"""
Embeddings для semantic search в аудио с кэшированием.
Reflexio v2.1 — lightweight-safe runtime by default.
"""
from typing import List, Dict, Any, Optional
from pathlib import Path
import hashlib
import json
import math
import os
import sqlite3

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


def _ensure_text_entries_table(db_path: Path | None = None) -> None:
    """Создаёт text_entries с колонкой metadata (если не существует).

    ПОЧЕМУ здесь, а не в миграциях: migration 0001 — PostgreSQL DDL (UUID, vector).
    SQLiteBackend создаёт таблицу лениво. Но schema не включает metadata →
    store_embeddings() INSERT падает. Эта функция — idempotent ensure.
    """
    if db_path is None:
        from src.utils.config import settings
        db_path = settings.STORAGE_PATH / "reflexio.db"

    from src.storage.db import get_connection
    conn = get_connection(db_path)

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS text_entries (
            id TEXT PRIMARY KEY,
            mission_id TEXT,
            content TEXT NOT NULL,
            embedding TEXT,
            metadata TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        )
        """
    )

    # ПОЧЕМУ ALTER TABLE: если таблица уже создана без metadata (старая миграция),
    # добавляем колонку. OperationalError = колонка уже есть — безопасно.
    try:
        conn.execute("ALTER TABLE text_entries ADD COLUMN metadata TEXT")
    except Exception:
        pass  # колонка уже существует (sqlite3 или sqlcipher3)

    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_text_entries_mission ON text_entries(mission_id)"
    )
    conn.commit()


# ПОЧЕМУ копия из semantic_memory.py, а не import: semantic_memory уже
# импортирует generate_embeddings из этого модуля → circular dependency.
# Функция тривиальная (10 строк), дублирование оправдано.
def _cosine(a: list[float], b: list[float]) -> float:
    """Cosine similarity между двумя векторами. Pure Python, без numpy."""
    if not a or not b:
        return 0.0
    n = min(len(a), len(b))
    if n == 0:
        return 0.0
    dot = sum(a[i] * b[i] for i in range(n))
    na = math.sqrt(sum(a[i] * a[i] for i in range(n)))
    nb = math.sqrt(sum(b[i] * b[i] for i in range(n)))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


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
        _ensure_text_entries_table()

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
    """Гибридный semantic+lexical поиск фраз.

    ПОЧЕМУ гибрид: чисто embedding-поиск может пропустить точные совпадения,
    чисто lexical (Ctrl+F) не найдёт синонимы. Формула: 0.7*cosine + 0.3*lexical.
    """
    try:
        _ensure_text_entries_table()

        if db_backend is None:
            from src.storage.db import get_db

            db_backend = get_db()

        query_emb = generate_embeddings(query)

        filters = {"mission_id": audio_id} if audio_id else None
        # ПОЧЕМУ limit*5: берём больше кандидатов для ранжирования,
        # потом отсекаем по score. При lexical-only limit*2 хватало,
        # для semantic нужен больший pool.
        entries = db_backend.select("text_entries", filters=filters, limit=limit * 5)

        scored: List[tuple[float, Dict[str, Any]]] = []
        for entry in entries:
            content = entry.get("content", "")
            if not content:
                continue

            # Парсим embedding из JSON string (SQLiteBackend хранит как TEXT)
            entry_emb: List[float] = []
            raw_emb = entry.get("embedding", "")
            if isinstance(raw_emb, str) and raw_emb:
                try:
                    entry_emb = json.loads(raw_emb)
                except (json.JSONDecodeError, TypeError):
                    pass
            elif isinstance(raw_emb, list):
                entry_emb = raw_emb

            # Парсим metadata из JSON string
            meta: Dict[str, Any] = {}
            raw_meta = entry.get("metadata", "")
            if isinstance(raw_meta, str) and raw_meta:
                try:
                    meta = json.loads(raw_meta)
                except (json.JSONDecodeError, TypeError):
                    pass
            elif isinstance(raw_meta, dict):
                meta = raw_meta

            lexical = 1.0 if query.lower() in content.lower() else 0.0
            semantic = _cosine(query_emb, entry_emb) if query_emb and entry_emb else 0.0
            score = semantic * 0.7 + lexical * 0.3

            item = {
                "text": content,
                "start": meta.get("start_time", 0.0),
                "end": meta.get("end_time", 0.0),
                "confidence": meta.get("confidence", 0.0),
                "score": round(score, 4),
            }
            scored.append((score, item))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [item for _, item in scored[:limit]]
    except Exception as e:
        logger.error("phrase_search_failed", error=str(e))
        return []

