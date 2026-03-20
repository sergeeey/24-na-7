"""User Profile — accumulated knowledge about the user from transcriptions.

WHY: Without a profile, enrichment treats every segment in isolation.
"Катерина" is just a name; with profile it's "wife Katerina" → richer digest.
Profile accumulates from:
1. Structured events (topics, people, commitments)
2. Episode patterns (work hours, home hours, topics by location)
3. Manual corrections (user says "that's my wife")
4. Speaker verification (who is OWNER vs others)
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.storage.db import get_reflexio_db
from src.storage.ingest_persist import ensure_ingest_tables
from src.utils.logging import get_logger

logger = get_logger("memory.user_profile")


# ── Profile Key-Value Store ──


def get_profile(db_path: Path) -> dict[str, Any]:
    """Return full user profile as a dict."""
    ensure_ingest_tables(db_path)
    db = get_reflexio_db(db_path)
    rows = db.fetchall("SELECT key, value, confidence, evidence_count FROM user_profile")
    return {
        row["key"]: {
            "value": row["value"],
            "confidence": row["confidence"],
            "evidence_count": row["evidence_count"],
        }
        for row in rows
    }


def set_profile_fact(
    db_path: Path,
    key: str,
    value: str,
    source: str = "auto",
    confidence: float = 0.5,
) -> None:
    """Set or update a profile fact. Higher confidence overwrites lower."""
    ensure_ingest_tables(db_path)
    db = get_reflexio_db(db_path)
    now = datetime.now(timezone.utc).isoformat()

    existing = db.fetchone(
        "SELECT confidence, evidence_count FROM user_profile WHERE key = ?", (key,)
    )

    if existing is None:
        db.execute(
            "INSERT INTO user_profile (key, value, source, confidence, updated_at, evidence_count) VALUES (?, ?, ?, ?, ?, 1)",
            (key, value, source, confidence, now),
        )
    else:
        new_count = existing["evidence_count"] + 1
        # WHY: manual corrections always win over auto-detected
        new_confidence = max(existing["confidence"], confidence)
        if source == "manual" or confidence >= existing["confidence"]:
            db.execute(
                "UPDATE user_profile SET value = ?, source = ?, confidence = ?, updated_at = ?, evidence_count = ? WHERE key = ?",
                (value, source, new_confidence, now, new_count, key),
            )
        else:
            # Just increment evidence count
            db.execute(
                "UPDATE user_profile SET evidence_count = ?, updated_at = ? WHERE key = ?",
                (new_count, now, key),
            )

    db.conn.commit()
    logger.info("profile_fact_set", key=key, value=value[:50], source=source, confidence=confidence)


# ── Known People Store ──


def get_known_people(db_path: Path) -> list[dict[str, Any]]:
    """Return all known people with relationship info."""
    ensure_ingest_tables(db_path)
    db = get_reflexio_db(db_path)
    rows = db.fetchall(
        "SELECT name, relationship, context, mention_count, last_mentioned_at, source FROM known_people ORDER BY mention_count DESC"
    )
    return [dict(row) for row in rows]


def upsert_person(
    db_path: Path,
    name: str,
    relationship: str = "unknown",
    context: str = "",
    source: str = "auto",
) -> None:
    """Add or update a known person. Auto sources increment count; manual sources set relationship."""
    ensure_ingest_tables(db_path)
    db = get_reflexio_db(db_path)
    now = datetime.now(timezone.utc).isoformat()

    existing = db.fetchone("SELECT * FROM known_people WHERE name = ?", (name,))

    if existing is None:
        db.execute(
            "INSERT INTO known_people (name, relationship, context, mention_count, last_mentioned_at, source) VALUES (?, ?, ?, 1, ?, ?)",
            (name, relationship, context, now, source),
        )
    else:
        new_count = existing["mention_count"] + 1
        # Manual source always overwrites auto relationship
        new_rel = (
            relationship
            if (source == "manual" or existing["source"] == "auto")
            else existing["relationship"]
        )
        new_ctx = context if context else existing["context"]
        db.execute(
            "UPDATE known_people SET relationship = ?, context = ?, mention_count = ?, last_mentioned_at = ?, source = ? WHERE name = ?",
            (
                new_rel,
                new_ctx,
                new_count,
                now,
                source if source == "manual" else existing["source"],
                name,
            ),
        )

    db.conn.commit()


# ── Auto-extraction from structured events ──


def extract_people_from_events(db_path: Path, since_hours: int = 24) -> int:
    """Scan recent structured events and extract people into known_people.

    WHY: speakers field in structured_events contains people mentioned in speech.
    By accumulating them, we build a social graph without manual input.
    """
    ensure_ingest_tables(db_path)
    db = get_reflexio_db(db_path)

    rows = db.fetchall(
        """
        SELECT speakers, topics, created_at
        FROM structured_events
        WHERE is_current = 1
          AND created_at >= datetime('now', ? || ' hours')
          AND speakers IS NOT NULL AND speakers != '[]'
        """,
        (f"-{since_hours}",),
    )

    count = 0
    for row in rows:
        try:
            speakers = (
                json.loads(row["speakers"]) if isinstance(row["speakers"], str) else row["speakers"]
            )
            topics = (
                json.loads(row["topics"])
                if isinstance(row["topics"], str)
                else (row["topics"] or [])
            )
        except (json.JSONDecodeError, TypeError):
            continue

        for speaker in speakers:
            name = str(speaker).strip()
            if len(name) < 2 or len(name) > 50:
                continue
            # WHY: topic context helps identify relationship
            # "бюджет, проект" → likely colleague, "дочка, купание" → likely family
            topic_str = ", ".join(str(t) for t in topics[:3]) if topics else ""
            upsert_person(db_path, name, context=topic_str, source="auto")
            count += 1

    logger.info("people_extracted", count=count, since_hours=since_hours)
    return count


def extract_profile_facts_from_events(db_path: Path, since_hours: int = 24) -> int:
    """Scan recent events for profile-relevant facts.

    Extracts: work_domain, top_topics, emotional_baseline, active_hours.
    """
    ensure_ingest_tables(db_path)
    db = get_reflexio_db(db_path)
    now = datetime.now(timezone.utc).isoformat()
    count = 0

    # Top topics → work domain inference
    topic_rows = db.fetchall(
        """
        SELECT topics FROM structured_events
        WHERE is_current = 1 AND created_at >= datetime('now', ? || ' hours')
        AND topics IS NOT NULL AND topics != '[]'
        """,
        (f"-{since_hours}",),
    )
    all_topics: dict[str, int] = {}
    for row in topic_rows:
        try:
            topics = json.loads(row["topics"]) if isinstance(row["topics"], str) else row["topics"]
            for t in topics:
                k = str(t).lower().strip()
                if len(k) > 2:
                    all_topics[k] = all_topics.get(k, 0) + 1
        except (json.JSONDecodeError, TypeError):
            continue

    if all_topics:
        top5 = sorted(all_topics.items(), key=lambda x: -x[1])[:5]
        set_profile_fact(
            db_path,
            "top_topics",
            json.dumps([t for t, _ in top5], ensure_ascii=False),
            confidence=0.7,
        )
        count += 1

    # Emotional baseline
    emo_rows = db.fetchall(
        """
        SELECT emotions FROM structured_events
        WHERE is_current = 1 AND created_at >= datetime('now', ? || ' hours')
        AND emotions IS NOT NULL AND emotions != '[]'
        """,
        (f"-{since_hours}",),
    )
    all_emotions: dict[str, int] = {}
    for row in emo_rows:
        try:
            emotions = (
                json.loads(row["emotions"]) if isinstance(row["emotions"], str) else row["emotions"]
            )
            for e in emotions:
                k = str(e).lower().strip()
                if len(k) > 2:
                    all_emotions[k] = all_emotions.get(k, 0) + 1
        except (json.JSONDecodeError, TypeError):
            continue

    if all_emotions:
        top3_emo = sorted(all_emotions.items(), key=lambda x: -x[1])[:3]
        set_profile_fact(
            db_path,
            "emotional_baseline",
            json.dumps([e for e, _ in top3_emo], ensure_ascii=False),
            confidence=0.6,
        )
        count += 1

    # Active hours
    hour_rows = db.fetchall(
        """
        SELECT created_at FROM structured_events
        WHERE is_current = 1 AND created_at >= datetime('now', ? || ' hours')
        """,
        (f"-{since_hours}",),
    )
    hours: dict[int, int] = {}
    for row in hour_rows:
        try:
            h = int(str(row["created_at"])[11:13])
            hours[h] = hours.get(h, 0) + 1
        except (ValueError, IndexError):
            continue

    if hours:
        active = sorted(hours.items(), key=lambda x: -x[1])[:3]
        set_profile_fact(
            db_path, "active_hours", json.dumps([h for h, _ in active]), confidence=0.6
        )
        count += 1

    logger.info("profile_facts_extracted", count=count, since_hours=since_hours)
    return count


# ── Profile for enrichment context ──


def get_enrichment_context(db_path: Path) -> str:
    """Build a short context string for LLM enrichment prompts.

    WHY: Without this, enrichment says "speaker discusses budget".
    With this: "Sergei (Head of Security, finance KZ) discusses budget with colleague Maksim Ilyich".
    """
    profile = get_profile(db_path)
    people = get_known_people(db_path)

    parts: list[str] = []

    name = profile.get("user_name", {}).get("value")
    if name:
        parts.append(f"Speaker: {name}")

    role = profile.get("work_role", {}).get("value")
    if role:
        parts.append(f"Role: {role}")

    top_topics = profile.get("top_topics", {}).get("value")
    if top_topics:
        try:
            topics = json.loads(top_topics)
            parts.append(f"Usual topics: {', '.join(topics[:3])}")
        except (json.JSONDecodeError, TypeError):
            pass

    if people:
        top_people = [p for p in people if p["mention_count"] >= 2][:5]
        if top_people:
            people_str = ", ".join(
                f"{p['name']} ({p['relationship']})"
                if p["relationship"] != "unknown"
                else p["name"]
                for p in top_people
            )
            parts.append(f"Known people: {people_str}")

    return ". ".join(parts) if parts else ""
