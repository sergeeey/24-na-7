"""Consumed Content Analysis — what the user watches, listens to, reads.

WHY: TV/YouTube/podcast content that the mic picks up is not the user's speech,
but it reveals interests, learning patterns, and mood. Instead of discarding
this as noise, we store and analyze it separately.

Source types:
- youtube: detected by subtitle markers ("субтитры", "подпишись", etc.)
- tv: detected by TV-specific phrases ("продолжение следует", etc.)
- podcast: longer monologue segments from non-owner speakers
- unknown: unclassified non-owner content
"""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.storage.db import get_reflexio_db
from src.storage.ingest_persist import ensure_ingest_tables
from src.utils.logging import get_logger

logger = get_logger("memory.consumed_content")

# WHY: These markers identify the SOURCE of consumed content.
# YouTube has specific subtitle patterns. TV has broadcast markers.
YOUTUBE_MARKERS = (
    "субтитры делал",
    "субтитры добавил",
    "субтитры подготовил",
    "спасибо за субтитры",
    "подпишись на канал",
    "подпишитесь на канал",
    "спасибо за просмотр",
    "ставь лайк",
    "жми на колокольчик",
    "не пропустить новые видео",
    "ссылка в описании",
)

TV_MARKERS = (
    "продолжение следует",
    "редактор субтитров",
    "корректор",
    "с вами был",
    "напряженная музыка",
    "полицейская сирена",
)


def classify_source(text: str) -> str:
    """Classify consumed content source type from text."""
    lower = text.lower()
    if any(m in lower for m in YOUTUBE_MARKERS):
        return "youtube"
    if any(m in lower for m in TV_MARKERS):
        return "tv"
    # Long monologues (>10 words) without owner markers → likely podcast/video
    if len(text.split()) > 15:
        return "podcast"
    return "unknown"


def extract_topics_simple(text: str) -> list[str]:
    """Extract simple topic keywords from consumed content.

    WHY: No LLM call — consumed content is high volume, LLM would be too expensive.
    Simple keyword extraction is enough for interest mapping.
    """
    # Remove common filler
    clean = re.sub(r"[^\w\s]", " ", text.lower())
    words = clean.split()

    # Filter: 4+ chars, not stopwords
    stopwords = {
        "это",
        "вот",
        "что",
        "как",
        "для",
        "при",
        "так",
        "уже",
        "его",
        "ещё",
        "они",
        "вас",
        "нас",
        "мне",
        "тебе",
        "себя",
        "свой",
        "свою",
        "свои",
        "будет",
        "было",
        "были",
        "есть",
        "этот",
        "этой",
        "этих",
        "этом",
        "того",
        "тоже",
        "очень",
        "просто",
        "когда",
        "потом",
        "после",
        "which",
        "that",
        "this",
        "with",
        "from",
        "have",
        "been",
        "will",
        "just",
        "your",
        "about",
        "more",
        "than",
        "also",
    }

    meaningful = [w for w in words if len(w) >= 4 and w not in stopwords]

    # Count and return top 5
    from collections import Counter

    counts = Counter(meaningful)
    return [word for word, _ in counts.most_common(5)]


def save_consumed_content(
    db_path: Path,
    text: str,
    language: str | None = None,
    duration: float | None = None,
) -> str | None:
    """Save a piece of consumed content (filtered non-owner speech).

    Returns content ID or None if text is too short.
    """
    if not text or len(text.strip()) < 5:
        return None

    ensure_ingest_tables(db_path)
    db = get_reflexio_db(db_path)

    content_id = str(uuid.uuid4())
    source_type = classify_source(text)
    topics = extract_topics_simple(text)
    now = datetime.now(timezone.utc).isoformat()

    db.execute(
        """
        INSERT INTO consumed_content (id, text, source_type, topics, language, duration, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            content_id,
            text.strip(),
            source_type,
            json.dumps(topics, ensure_ascii=False),
            language,
            duration,
            now,
        ),
    )
    db.conn.commit()

    logger.debug("consumed_content_saved", id=content_id, source=source_type, topics=topics[:3])
    return content_id


def get_content_summary(db_path: Path, hours: int = 24) -> dict[str, Any]:
    """Summarize consumed content for the last N hours.

    Returns: source breakdown, top topics, total duration, content count.
    """
    ensure_ingest_tables(db_path)
    db = get_reflexio_db(db_path)

    rows = db.fetchall(
        """
        SELECT source_type, topics, duration, text
        FROM consumed_content
        WHERE created_at >= datetime('now', ? || ' hours')
        ORDER BY created_at DESC
        """,
        (f"-{hours}",),
    )

    if not rows:
        return {
            "total_count": 0,
            "total_duration_min": 0,
            "sources": {},
            "top_topics": [],
            "sample_texts": [],
        }

    # Source breakdown
    sources: dict[str, int] = {}
    all_topics: dict[str, int] = {}
    total_duration = 0.0
    sample_texts: list[str] = []

    for row in rows:
        src = row["source_type"] or "unknown"
        sources[src] = sources.get(src, 0) + 1

        try:
            topics = json.loads(row["topics"]) if isinstance(row["topics"], str) else []
            for t in topics:
                all_topics[t] = all_topics.get(t, 0) + 1
        except (json.JSONDecodeError, TypeError):
            pass

        if row["duration"]:
            total_duration += row["duration"]

        text = (row["text"] or "").strip()
        if len(text) > 20 and len(sample_texts) < 5:
            sample_texts.append(text[:100])

    top_topics = [t for t, _ in sorted(all_topics.items(), key=lambda x: -x[1])[:10]]

    return {
        "total_count": len(rows),
        "total_duration_min": round(total_duration / 60, 1),
        "sources": sources,
        "top_topics": top_topics,
        "sample_texts": sample_texts,
    }
