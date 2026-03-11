"""Rule-based episode builder for grouping nearby transcriptions into episodic memory."""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from src.enrichment.schema import StructuredEvent
from src.storage.db import get_reflexio_db
from src.storage.ingest_persist import ensure_ingest_tables, persist_structured_event
from src.utils.logging import get_logger

logger = get_logger("memory.episodes")

MERGE_WINDOW_SECONDS = 90
TOPIC_WORD_RE = re.compile(r"[A-Za-zА-Яа-яЁё0-9]{3,}")
STOP_WORDS = {
    "это",
    "как",
    "что",
    "или",
    "его",
    "еще",
    "ещё",
    "для",
    "про",
    "если",
    "потом",
    "тогда",
    "there",
    "with",
    "from",
    "this",
    "that",
    "have",
    "just",
}
THREAD_CONFIDENCE_THRESHOLD = 0.45
THREAD_TRUSTED_CONFIDENCE_THRESHOLD = 0.7
LONG_THREAD_CONFIDENCE_THRESHOLD = 0.5
LONG_THREAD_ACTIVE_DAYS = 7


def _parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _day_key(ts: datetime) -> str:
    return ts.date().isoformat()


def _safe_json_list(value: str | None) -> list[Any]:
    try:
        parsed = json.loads(value or "[]")
        return parsed if isinstance(parsed, list) else []
    except json.JSONDecodeError:
        return []


def _topic_tokens(*values: str | None) -> set[str]:
    tokens: set[str] = set()
    for value in values:
        if not value:
            continue
        for token in TOPIC_WORD_RE.findall(value.lower()):
            if token not in STOP_WORDS:
                tokens.add(token)
    return tokens


def _normalize_people(items: list[Any]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for item in items:
        if isinstance(item, str):
            candidate = item.strip()
        elif isinstance(item, dict):
            candidate = str(item.get("person") or item.get("name") or "").strip()
        else:
            candidate = ""
        if candidate and candidate.lower() not in seen:
            seen.add(candidate.lower())
            out.append(candidate)
    return out


def _overlap_score(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def _commitment_keys(items: list[Any]) -> set[str]:
    keys: set[str] = set()
    for item in items:
        if isinstance(item, str):
            candidate = item.strip().lower()
        elif isinstance(item, dict):
            candidate = str(item.get("text") or item.get("task") or item.get("person") or "").strip().lower()
        else:
            candidate = ""
        if candidate:
            keys.add(candidate)
    return keys


def _temporal_score(previous_end: datetime | None, current_start: datetime | None) -> float:
    if not previous_end or not current_start:
        return 0.0
    delta = max((current_start - previous_end).total_seconds(), 0.0)
    if delta <= 0:
        return 1.0
    if delta >= 4 * 3600:
        return 0.0
    return round(max(0.0, 1.0 - (delta / (4 * 3600))), 3)


def _temporal_day_score(previous_day: str | None, current_day: str | None) -> float:
    if not previous_day or not current_day:
        return 0.0
    try:
        previous = datetime.fromisoformat(previous_day)
        current = datetime.fromisoformat(current_day)
    except ValueError:
        return 0.0
    delta_days = abs((current.date() - previous.date()).days)
    if delta_days == 0:
        return 1.0
    if delta_days >= 30:
        return 0.0
    return round(max(0.0, 1.0 - (delta_days / 30)), 3)


def _score_episode_for_thread(candidate: dict[str, Any], episode: dict[str, Any]) -> dict[str, float]:
    candidate_topics = _topic_tokens(candidate.get("clean_text"), candidate.get("summary"), json.dumps(candidate.get("topics", []), ensure_ascii=False))
    episode_topics = _topic_tokens(episode.get("clean_text"), episode.get("summary"), json.dumps(episode.get("topics", []), ensure_ascii=False))
    topic_overlap = _overlap_score(candidate_topics, episode_topics)
    participant_overlap = _overlap_score(
        {p.lower() for p in candidate.get("participants", [])},
        {p.lower() for p in episode.get("participants", [])},
    )
    commitment_overlap = _overlap_score(
        _commitment_keys(candidate.get("commitments", [])),
        _commitment_keys(episode.get("commitments", [])),
    )
    temporal_proximity = _temporal_score(
        _parse_ts(candidate.get("ended_at")),
        _parse_ts(episode.get("started_at")),
    )
    thread_confidence = round(
        topic_overlap * 0.4
        + participant_overlap * 0.25
        + temporal_proximity * 0.25
        + commitment_overlap * 0.1,
        3,
    )
    return {
        "topic_overlap_score": round(topic_overlap, 3),
        "participant_overlap_score": round(participant_overlap, 3),
        "temporal_proximity_score": round(temporal_proximity, 3),
        "commitment_overlap_score": round(commitment_overlap, 3),
        "thread_confidence": thread_confidence,
    }


def _score_day_thread_for_long_thread(candidate: dict[str, Any], thread: dict[str, Any]) -> dict[str, float]:
    candidate_topics = _topic_tokens(
        candidate.get("summary"),
        json.dumps(candidate.get("topics", []), ensure_ascii=False),
    )
    thread_topics = _topic_tokens(
        thread.get("summary"),
        json.dumps(thread.get("topics", []), ensure_ascii=False),
    )
    topic_overlap = _overlap_score(candidate_topics, thread_topics)
    participant_overlap = _overlap_score(
        {p.lower() for p in candidate.get("participants", [])},
        {p.lower() for p in thread.get("participants", [])},
    )
    commitment_overlap = _overlap_score(
        _commitment_keys(candidate.get("commitments", [])),
        _commitment_keys(thread.get("commitments", [])),
    )
    temporal_proximity = _temporal_day_score(candidate.get("last_day_key"), thread.get("day_key"))
    continuity_score = round(
        topic_overlap * 0.4
        + participant_overlap * 0.3
        + commitment_overlap * 0.2
        + temporal_proximity * 0.1,
        3,
    )
    return {
        "topic_overlap_score": round(topic_overlap, 3),
        "participant_overlap_score": round(participant_overlap, 3),
        "temporal_proximity_score": round(temporal_proximity, 3),
        "commitment_overlap_score": round(commitment_overlap, 3),
        "continuity_score": continuity_score,
    }


def _close_stale_episodes(db_path: Path, now: datetime) -> int:
    db = get_reflexio_db(db_path)
    cutoff = (now - timedelta(seconds=MERGE_WINDOW_SECONDS)).isoformat()
    rows = db.fetchall(
        """
        SELECT id, day_key
        FROM episodes
        WHERE status='open' AND ended_at < ?
        ORDER BY ended_at ASC
        """,
        (cutoff,),
    )
    with db.transaction():
        result = db.execute(
            """
            UPDATE episodes
            SET status='closed'
            WHERE status='open' AND ended_at < ?
            """,
            (cutoff,),
        )
    closed = result.rowcount if hasattr(result, "rowcount") and result.rowcount is not None else len(rows)
    if closed:
        logger.info(
            "episodes_closed_stale",
            count=closed,
            cutoff=cutoff,
            episode_ids=[row["id"] for row in rows[:10]],
            day_keys=sorted({row["day_key"] for row in rows if row["day_key"]}),
        )
    return closed


def close_stale_episodes(db_path: Path, now: datetime | None = None) -> int:
    """Public wrapper for episode inactivity timeout closure."""
    return _close_stale_episodes(db_path, now or datetime.utcnow())


def finalize_closed_episodes(db_path: Path) -> int:
    """Create final current event versions for closed episodes and mark them summarized."""
    ensure_ingest_tables(db_path)
    db = get_reflexio_db(db_path)
    rows = db.fetchall(
        """
        SELECT e.id,
               e.started_at,
               e.ended_at,
               e.summary,
               e.clean_text,
               e.raw_text,
               e.topics_json,
               e.participants_json,
               e.commitments_json,
               e.needs_review,
               e.importance_score,
               e.transcription_ids_json,
               se.id AS current_event_id,
               se.transcription_id,
               se.timestamp,
               se.duration_sec,
               se.text,
               se.language,
               se.summary AS event_summary,
               se.emotions,
               se.topics,
               se.domains,
               se.tasks,
               se.commitments,
               se.decisions,
               se.speakers,
               se.urgency,
               se.sentiment,
               se.location,
               se.asr_confidence,
               se.enrichment_confidence,
               se.enrichment_model,
               se.enrichment_tokens,
               se.enrichment_latency_ms,
               se.pitch_hz_mean,
               se.pitch_variance,
               se.energy_mean,
               se.spectral_centroid_mean,
               se.acoustic_arousal,
               se.enrichment_prompt_hash,
               se.enrichment_version
        FROM episodes e
        JOIN structured_events se
          ON se.episode_id = e.id
         AND se.is_current = 1
        WHERE e.status = 'closed'
        ORDER BY e.started_at ASC
        """
    )

    finalized = 0
    affected_days: set[str] = set()
    for row in rows:
        transcription_ids = _safe_json_list(row["transcription_ids_json"])
        representative_transcription_id = (
            row["transcription_id"]
            or (transcription_ids[0] if transcription_ids else None)
        )
        if not representative_transcription_id:
            continue

        started_at = _parse_ts(row["started_at"]) or datetime.utcnow()
        ended_at = _parse_ts(row["ended_at"]) or started_at
        duration_sec = max((ended_at - started_at).total_seconds(), 0.0)
        clean_text = (row["clean_text"] or row["raw_text"] or row["text"] or "").strip()
        if not clean_text:
            continue

        event = StructuredEvent(
            id=str(uuid.uuid4()),
            transcription_id=representative_transcription_id,
            episode_id=row["id"],
            timestamp=started_at,
            duration_sec=duration_sec or float(row["duration_sec"] or 0.0),
            text=clean_text,
            language=row["language"] or "unknown",
            summary=(row["summary"] or row["event_summary"] or "").strip(),
            emotions=[str(v) for v in _safe_json_list(row["emotions"])],
            topics=[str(v) for v in (_safe_json_list(row["topics_json"]) or _safe_json_list(row["topics"]))],
            domains=[str(v) for v in _safe_json_list(row["domains"])],
            tasks=_safe_json_list(row["tasks"]),
            commitments=_safe_json_list(row["commitments_json"]) or _safe_json_list(row["commitments"]),
            decisions=[str(v) for v in _safe_json_list(row["decisions"])],
            speakers=[str(v) for v in (_safe_json_list(row["participants_json"]) or _safe_json_list(row["speakers"]))],
            urgency=row["urgency"] or "medium",
            sentiment=row["sentiment"] or "neutral",
            location=row["location"],
            pitch_hz_mean=row["pitch_hz_mean"],
            pitch_variance=row["pitch_variance"],
            energy_mean=row["energy_mean"],
            spectral_centroid_mean=row["spectral_centroid_mean"],
            acoustic_arousal=row["acoustic_arousal"],
            asr_confidence=float(row["asr_confidence"] or 0.0),
            enrichment_confidence=float(row["enrichment_confidence"] or row["importance_score"] or 0.0),
            enrichment_model=row["enrichment_model"] or "",
            enrichment_tokens=int(row["enrichment_tokens"] or 0),
            enrichment_latency_ms=float(row["enrichment_latency_ms"] or 0.0),
            enrichment_prompt_hash=row["enrichment_prompt_hash"],
            enrichment_version=((row["enrichment_version"] or "episode-aware") + "|episode_finalizer").strip("|"),
        )
        persist_structured_event(db_path, event)
        with db.transaction():
            db.execute(
                "UPDATE episodes SET status='summarized' WHERE id = ? AND status = 'closed'",
                (row["id"],),
            )
        finalized += 1
        day_key = _day_key(started_at)
        affected_days.add(day_key)
        logger.info(
            "episode_summarized",
            episode_id=row["id"],
            transcription_id=representative_transcription_id,
            day_key=day_key,
            duration_sec=round(duration_sec, 3),
        )

    for day_key in sorted(affected_days):
        rebuild_day_threads_for_day(db_path, day_key)

    return finalized


def get_episode_context(db_path: Path, episode_id: str | None) -> dict[str, Any] | None:
    """Return episode payload for episode-aware enrichment/digest consumers."""
    if not episode_id:
        return None
    ensure_ingest_tables(db_path)
    db = get_reflexio_db(db_path)
    row = db.fetchone(
        """
        SELECT id, started_at, ended_at, status, source_count, transcription_ids_json,
               raw_text, clean_text, summary, topics_json, participants_json,
               commitments_json, importance_score, needs_review, quality_state,
               quality_score, quality_reasons_json, review_required, day_key, thread_key
        FROM episodes
        WHERE id = ?
        LIMIT 1
        """,
        (episode_id,),
    )
    return dict(row) if row else None


def attach_transcription_to_episode(db_path: Path, transcription_id: str) -> str | None:
    """Attach transcription to an open episode or create a new one."""
    ensure_ingest_tables(db_path)
    db = get_reflexio_db(db_path)
    row = db.fetchone(
        """
        SELECT t.id,
               t.ingest_id,
               t.text,
               t.transcript_raw,
               t.transcript_clean,
               t.quality_score,
               t.needs_recheck,
               t.quality_state,
               t.quality_reasons_json,
               t.review_required,
               COALESCE(i.captured_at, t.created_at) AS effective_ts
        FROM transcriptions t
        LEFT JOIN ingest_queue i ON t.ingest_id = i.id
        WHERE t.id = ?
        LIMIT 1
        """,
        (transcription_id,),
    )
    if not row:
        return None

    text = row["transcript_clean"] or row["text"] or ""
    ts = _parse_ts(row["effective_ts"]) or datetime.utcnow()
    day_key = _day_key(ts)
    candidate_tokens = _topic_tokens(text)
    _close_stale_episodes(db_path, ts)

    candidates = db.fetchall(
        """
        SELECT id, started_at, ended_at, transcription_ids_json, raw_text, clean_text,
               topics_json, participants_json, commitments_json, importance_score, needs_review,
               quality_state, quality_score, quality_reasons_json, review_required
        FROM episodes
        WHERE status='open' AND day_key = ?
        ORDER BY ended_at DESC
        LIMIT 5
        """,
        (day_key,),
    )

    chosen: dict[str, Any] | None = None
    for candidate in candidates:
        ended_at = _parse_ts(candidate["ended_at"])
        if ended_at is None:
            continue
        if (ts - ended_at).total_seconds() > MERGE_WINDOW_SECONDS:
            continue
        existing_tokens = _topic_tokens(candidate["clean_text"], candidate["raw_text"])
        topic_overlap = bool(candidate_tokens & existing_tokens) if candidate_tokens and existing_tokens else True
        if topic_overlap:
            chosen = dict(candidate)
            break

    with db.transaction():
        if chosen:
            transcription_ids = _safe_json_list(chosen["transcription_ids_json"])
            if transcription_id not in transcription_ids:
                transcription_ids.append(transcription_id)
            raw_text = "\n".join(filter(None, [chosen["raw_text"], row["transcript_raw"] or text])).strip()
            clean_text = "\n".join(filter(None, [chosen["clean_text"], text])).strip()
            db.execute(
                """
                UPDATE episodes
                SET ended_at = ?,
                    source_count = ?,
                    transcription_ids_json = ?,
                    raw_text = ?,
                    clean_text = ?,
                    importance_score = MAX(COALESCE(importance_score, 0), COALESCE(?, 0)),
                    needs_review = CASE WHEN COALESCE(needs_review, 0) = 1 OR ? = 1 THEN 1 ELSE 0 END
                WHERE id = ?
                """,
                (
                    ts.isoformat(),
                    len(transcription_ids),
                    json.dumps(transcription_ids),
                    raw_text,
                    clean_text,
                    row["quality_score"],
                    1 if row["needs_recheck"] else 0,
                    chosen["id"],
                ),
            )
            episode_id = chosen["id"]
            logger.info(
                "episode_extended",
                episode_id=episode_id,
                transcription_id=transcription_id,
                source_count=len(transcription_ids),
                day_key=day_key,
            )
        else:
            episode_id = str(uuid.uuid4())
            db.execute(
                """
                INSERT INTO episodes (
                    id, started_at, ended_at, status, source_count, transcription_ids_json,
                    raw_text, clean_text, summary, topics_json, participants_json,
                    commitments_json, importance_score, needs_review, day_key, thread_key
                ) VALUES (?, ?, ?, 'open', ?, ?, ?, ?, '', '[]', '[]', '[]', ?, ?, ?, NULL)
                """,
                (
                    episode_id,
                    ts.isoformat(),
                    ts.isoformat(),
                    1,
                    json.dumps([transcription_id]),
                    row["transcript_raw"] or text,
                    text,
                    row["quality_score"] or 0.0,
                    1 if row["needs_recheck"] else 0,
                    day_key,
                ),
            )
            logger.info(
                "episode_created",
                episode_id=episode_id,
                transcription_id=transcription_id,
                day_key=day_key,
            )

        db.execute(
            "UPDATE transcriptions SET episode_id = ? WHERE id = ?",
            (episode_id, transcription_id),
        )

    rebuild_day_threads_for_day(db_path, day_key)
    logger.info("episode_attached", transcription_id=transcription_id, episode_id=episode_id)
    return episode_id


def refresh_episode_from_event(db_path: Path, transcription_id: str, event: Any) -> str | None:
    """Refresh episode payload after enrichment and rebuild day threads."""
    ensure_ingest_tables(db_path)
    db = get_reflexio_db(db_path)
    row = db.fetchone(
        "SELECT episode_id FROM transcriptions WHERE id = ? LIMIT 1",
        (transcription_id,),
    )
    if not row or not row["episode_id"]:
        return None

    episode_id = row["episode_id"]
    topic_candidates = list(getattr(event, "topics", []) or [])
    speaker_candidates = list(getattr(event, "speakers", []) or [])
    speaker_candidates.extend(_normalize_people(getattr(event, "commitments", []) or []))
    commitment_payload = [
        c.model_dump() if hasattr(c, "model_dump") else c
        for c in (getattr(event, "commitments", []) or [])
    ]

    current = db.fetchone(
        """
        SELECT topics_json, participants_json, commitments_json, summary, clean_text, day_key
             , quality_state, quality_score, quality_reasons_json, review_required
        FROM episodes WHERE id = ?
        """,
        (episode_id,),
    )
    if not current:
        return episode_id

    merged_topics = list(dict.fromkeys(_safe_json_list(current["topics_json"]) + topic_candidates))
    merged_people = _normalize_people(_safe_json_list(current["participants_json"]) + speaker_candidates)
    merged_commitments = _safe_json_list(current["commitments_json"]) + commitment_payload
    summary = (getattr(event, "summary", "") or current["summary"] or "").strip()
    clean_text = "\n".join(
        filter(None, [current["clean_text"], getattr(event, "text", "") or ""])
    ).strip()

    with db.transaction():
        db.execute(
            """
            UPDATE episodes
            SET summary = ?,
                clean_text = ?,
                topics_json = ?,
                participants_json = ?,
                commitments_json = ?,
                importance_score = MAX(COALESCE(importance_score, 0), COALESCE(?, 0)),
                needs_review = CASE WHEN COALESCE(needs_review, 0) = 1 OR ? = 1 THEN 1 ELSE 0 END
            WHERE id = ?
            """,
            (
                summary,
                clean_text,
                json.dumps(merged_topics),
                json.dumps(merged_people),
                json.dumps(merged_commitments),
                getattr(event, "enrichment_confidence", 0.0),
                1 if getattr(event, "enrichment_confidence", 0.0) < 0.5 else 0,
                episode_id,
            ),
        )
    rebuild_day_threads_for_day(db_path, current["day_key"])
    return episode_id


def rebuild_day_threads_for_day(db_path: Path, day_key: str) -> None:
    """Cluster trusted summarized episodes into day-level storyline threads."""
    ensure_ingest_tables(db_path)
    db = get_reflexio_db(db_path)
    rows = db.fetchall(
        """
        SELECT id, started_at, ended_at, summary, clean_text, topics_json,
               participants_json, commitments_json, quality_state, status
        FROM episodes
        WHERE day_key = ?
          AND status = 'summarized'
          AND COALESCE(quality_state, 'trusted') = 'trusted'
        ORDER BY started_at ASC
        """,
        (day_key,),
    )
    episodes = []
    for row in rows:
        episode = dict(row)
        episode["topics"] = [str(v) for v in _safe_json_list(episode.get("topics_json"))]
        episode["participants"] = _normalize_people(_safe_json_list(episode.get("participants_json")))
        episode["commitments"] = _safe_json_list(episode.get("commitments_json"))
        episodes.append(episode)

    threads: list[dict[str, Any]] = []
    for episode in episodes:
        best_thread: dict[str, Any] | None = None
        best_scores: dict[str, float] | None = None
        for thread in threads:
            scores = _score_episode_for_thread(thread, episode)
            if scores["thread_confidence"] < THREAD_CONFIDENCE_THRESHOLD:
                continue
            if best_scores is None or scores["thread_confidence"] > best_scores["thread_confidence"]:
                best_thread = thread
                best_scores = scores

        if best_thread and best_scores:
            best_thread["episode_ids"].append(episode["id"])
            if episode.get("summary"):
                best_thread["summaries"].append(episode["summary"])
            best_thread["topics"].extend(episode["topics"])
            best_thread["participants"].extend(episode["participants"])
            best_thread["commitments"].extend(episode["commitments"])
            best_thread["ended_at"] = episode.get("ended_at")
            count = len(best_thread["episode_ids"])
            for key, value in best_scores.items():
                best_thread[key] = round(((best_thread.get(key, 0.0) * (count - 1)) + value) / count, 3)
        else:
            thread_id = str(uuid.uuid4())
            threads.append(
                {
                    "id": thread_id,
                    "episode_ids": [episode["id"]],
                    "summaries": [episode["summary"]] if episode.get("summary") else [],
                    "topics": list(episode["topics"]),
                    "participants": list(episode["participants"]),
                    "commitments": list(episode["commitments"]),
                    "started_at": episode.get("started_at"),
                    "ended_at": episode.get("ended_at"),
                    "topic_overlap_score": 1.0 if episode["topics"] else 0.0,
                    "participant_overlap_score": 1.0 if episode["participants"] else 0.0,
                    "temporal_proximity_score": 1.0,
                    "commitment_overlap_score": 1.0 if episode["commitments"] else 0.0,
                    "thread_confidence": 1.0 if episode["topics"] or episode["participants"] or episode["commitments"] else 0.55,
                }
            )

    with db.transaction():
        db.execute("UPDATE episodes SET thread_key = NULL WHERE day_key = ?", (day_key,))
        db.execute("DELETE FROM day_threads WHERE day_key = ?", (day_key,))
        for thread in threads:
            topic_candidates = [topic for topic in thread["topics"] if topic]
            topic_cluster = topic_candidates[0] if topic_candidates else "general"
            summary = " ".join(thread["summaries"][:3]).strip()
            commitments_json = json.dumps(thread["commitments"])
            topics_json = json.dumps(list(dict.fromkeys(topic_candidates)))
            participants_json = json.dumps(_normalize_people(thread["participants"]))
            thread_id = thread["id"]
            db.execute(
                """
                INSERT INTO day_threads (
                    id, day_key, topic_cluster, episode_ids_json, summary,
                    open_questions, commitments_json, topics_json, participants_json, carryover_candidate,
                    topic_overlap_score, participant_overlap_score,
                    temporal_proximity_score, commitment_overlap_score,
                    thread_confidence
                ) VALUES (?, ?, ?, ?, ?, '', ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    thread_id,
                    day_key,
                    topic_cluster or "general",
                    json.dumps(thread["episode_ids"]),
                    summary,
                    commitments_json,
                    topics_json,
                    participants_json,
                    1 if thread["commitments"] else 0,
                    thread["topic_overlap_score"],
                    thread["participant_overlap_score"],
                    thread["temporal_proximity_score"],
                    thread["commitment_overlap_score"],
                    thread["thread_confidence"],
                ),
            )
            for episode_id in thread["episode_ids"]:
                db.execute(
                    "UPDATE episodes SET thread_key = ? WHERE id = ?",
                    (thread_id, episode_id),
                )
    rebuild_long_threads_for_window(db_path, day_key)
    if threads or episodes:
        trusted_threads = sum(
            1 for thread in threads
            if float(thread.get("thread_confidence") or 0.0) >= THREAD_TRUSTED_CONFIDENCE_THRESHOLD
        )
        logger.info(
            "day_threads_rebuilt",
            day_key=day_key,
            episode_count=len(episodes),
            thread_count=len(threads),
            trusted_thread_count=trusted_threads,
            low_confidence_thread_count=max(len(threads) - trusted_threads, 0),
        )


def get_day_threads_for_day(db_path: Path, day_key: str) -> list[dict[str, Any]]:
    ensure_ingest_tables(db_path)
    db = get_reflexio_db(db_path)
    rows = db.fetchall(
        """
        SELECT id, day_key, topic_cluster, episode_ids_json, summary, open_questions,
               commitments_json, topics_json, participants_json, carryover_candidate, long_thread_key, topic_overlap_score,
               participant_overlap_score, temporal_proximity_score,
               commitment_overlap_score, thread_confidence
        FROM day_threads
        WHERE day_key = ?
        ORDER BY thread_confidence DESC, id ASC
        """,
        (day_key,),
    )
    return [dict(row) for row in rows]


def get_episodes_for_day(db_path: Path, day_key: str) -> list[dict[str, Any]]:
    ensure_ingest_tables(db_path)
    db = get_reflexio_db(db_path)
    rows = db.fetchall(
        """
        SELECT id, started_at, ended_at, status, source_count, transcription_ids_json,
               raw_text, clean_text, summary, topics_json, participants_json,
               commitments_json, importance_score, needs_review, quality_state,
               quality_score, quality_reasons_json, review_required, day_key, thread_key, long_thread_key
        FROM episodes
        WHERE day_key = ?
        ORDER BY started_at ASC
        """,
        (day_key,),
    )
    return [dict(row) for row in rows]


def rebuild_long_threads_for_window(db_path: Path, anchor_day_key: str, lookback_days: int = 30) -> None:
    ensure_ingest_tables(db_path)
    db = get_reflexio_db(db_path)
    anchor_dt = datetime.fromisoformat(anchor_day_key)
    start_day_key = (anchor_dt - timedelta(days=lookback_days)).date().isoformat()
    rows = db.fetchall(
        """
        SELECT id, day_key, topic_cluster, summary, episode_ids_json, commitments_json,
               topics_json, participants_json, thread_confidence
        FROM day_threads
        WHERE day_key BETWEEN ? AND ?
          AND thread_confidence >= ?
        ORDER BY day_key ASC, id ASC
        """,
        (start_day_key, anchor_day_key, THREAD_TRUSTED_CONFIDENCE_THRESHOLD),
    )
    threads: list[dict[str, Any]] = []
    for row in rows:
        candidate = dict(row)
        candidate["topics"] = [str(v) for v in _safe_json_list(candidate.get("topics_json"))]
        candidate["participants"] = _normalize_people(_safe_json_list(candidate.get("participants_json")))
        candidate["commitments"] = _safe_json_list(candidate.get("commitments_json"))
        candidate["episode_ids"] = _safe_json_list(candidate.get("episode_ids_json"))
        best_thread: dict[str, Any] | None = None
        best_scores: dict[str, float] | None = None
        for existing in threads:
            scores = _score_day_thread_for_long_thread(existing, candidate)
            if scores["continuity_score"] < LONG_THREAD_CONFIDENCE_THRESHOLD:
                continue
            if best_scores is None or scores["continuity_score"] > best_scores["continuity_score"]:
                best_thread = existing
                best_scores = scores
        if best_thread and best_scores:
            best_thread["day_thread_ids"].append(candidate["id"])
            best_thread["topics"].extend(candidate["topics"])
            best_thread["participants"].extend(candidate["participants"])
            best_thread["commitments"].extend(candidate["commitments"])
            if candidate.get("summary"):
                best_thread["summaries"].append(candidate["summary"])
            best_thread["last_seen_at"] = candidate["day_key"]
            best_thread["last_day_key"] = candidate["day_key"]
            count = len(best_thread["day_thread_ids"])
            for key, value in best_scores.items():
                best_thread[key] = round(((best_thread.get(key, 0.0) * (count - 1)) + value) / count, 3)
        else:
            threads.append(
                {
                    "id": str(uuid.uuid4()),
                    "thread_key": str(uuid.uuid4()),
                    "day_thread_ids": [candidate["id"]],
                    "topics": list(candidate["topics"]),
                    "participants": list(candidate["participants"]),
                    "commitments": list(candidate["commitments"]),
                    "summaries": [candidate["summary"]] if candidate.get("summary") else [],
                    "first_seen_at": candidate["day_key"],
                    "last_seen_at": candidate["day_key"],
                    "last_day_key": candidate["day_key"],
                    "status": "active",
                    "continuity_score": 1.0 if candidate["topics"] or candidate["participants"] or candidate["commitments"] else 0.6,
                }
            )

    with db.transaction():
        db.execute(
            "UPDATE day_threads SET long_thread_key = NULL WHERE day_key BETWEEN ? AND ?",
            (start_day_key, anchor_day_key),
        )
        db.execute(
            "UPDATE episodes SET long_thread_key = NULL WHERE day_key BETWEEN ? AND ?",
            (start_day_key, anchor_day_key),
        )
        db.execute(
            "DELETE FROM long_threads WHERE first_seen_at >= ? AND last_seen_at <= ?",
            (start_day_key, anchor_day_key),
        )
        for thread in threads:
            status = "active"
            if _temporal_day_score(thread["last_seen_at"], anchor_day_key) == 0.0:
                status = "dormant"
            elif abs((anchor_dt.date() - datetime.fromisoformat(thread["last_seen_at"]).date()).days) > LONG_THREAD_ACTIVE_DAYS:
                status = "dormant"
            summary = " ".join(thread["summaries"][:3]).strip()
            topics = list(dict.fromkeys([topic for topic in thread["topics"] if topic]))
            participants = _normalize_people(thread["participants"])
            db.execute(
                """
                INSERT INTO long_threads (
                    id, thread_key, first_seen_at, last_seen_at, day_thread_ids_json,
                    participants_json, topics_json, status, summary, continuity_score
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    thread["id"],
                    thread["thread_key"],
                    thread["first_seen_at"],
                    thread["last_seen_at"],
                    json.dumps(thread["day_thread_ids"]),
                    json.dumps(participants),
                    json.dumps(topics),
                    status,
                    summary,
                    round(float(thread.get("continuity_score") or 0.0), 3),
                ),
            )
            for day_thread_id in thread["day_thread_ids"]:
                db.execute(
                    "UPDATE day_threads SET long_thread_key = ? WHERE id = ?",
                    (thread["id"], day_thread_id),
                )
            day_thread_ids = tuple(thread["day_thread_ids"])
            if day_thread_ids:
                placeholders = ",".join("?" for _ in day_thread_ids)
                db.execute(
                    f"""
                    UPDATE episodes
                    SET long_thread_key = ?
                    WHERE thread_key IN ({placeholders})
                    """,
                    (thread["id"], *day_thread_ids),
                )
    if rows:
        logger.info(
            "long_threads_rebuilt",
            anchor_day_key=anchor_day_key,
            start_day_key=start_day_key,
            day_thread_count=len(rows),
            long_thread_count=len(threads),
            active_count=sum(1 for thread in threads if thread.get("status", "active") == "active"),
        )


def get_long_threads(db_path: Path) -> list[dict[str, Any]]:
    ensure_ingest_tables(db_path)
    db = get_reflexio_db(db_path)
    rows = db.fetchall(
        """
        SELECT id, thread_key, first_seen_at, last_seen_at, day_thread_ids_json,
               participants_json, topics_json, status, summary, continuity_score
        FROM long_threads
        ORDER BY last_seen_at DESC, continuity_score DESC, id ASC
        """
    )
    return [dict(row) for row in rows]


def get_long_thread_details(db_path: Path, long_thread_id: str) -> dict[str, Any] | None:
    """Expand a long thread into linked day threads and episodes."""
    ensure_ingest_tables(db_path)
    db = get_reflexio_db(db_path)
    row = db.fetchone(
        """
        SELECT id, thread_key, first_seen_at, last_seen_at, day_thread_ids_json,
               participants_json, topics_json, status, summary, continuity_score
        FROM long_threads
        WHERE id = ?
        LIMIT 1
        """,
        (long_thread_id,),
    )
    if not row:
        return None

    payload = dict(row)
    day_thread_ids = [str(v) for v in _safe_json_list(payload.get("day_thread_ids_json")) if str(v).strip()]
    payload["day_thread_ids"] = day_thread_ids
    payload["participants"] = _normalize_people(_safe_json_list(payload.get("participants_json")))
    payload["topics"] = [str(v) for v in _safe_json_list(payload.get("topics_json")) if str(v).strip()]

    day_threads: list[dict[str, Any]] = []
    episode_ids: list[str] = []
    for day_thread_id in day_thread_ids:
        thread_row = db.fetchone(
            """
            SELECT id, day_key, topic_cluster, episode_ids_json, summary, open_questions,
                   commitments_json, topics_json, participants_json, carryover_candidate,
                   long_thread_key, topic_overlap_score, participant_overlap_score,
                   temporal_proximity_score, commitment_overlap_score, thread_confidence
            FROM day_threads
            WHERE id = ?
            LIMIT 1
            """,
            (day_thread_id,),
        )
        if not thread_row:
            continue
        thread_payload = dict(thread_row)
        thread_payload["episode_ids"] = [str(v) for v in _safe_json_list(thread_payload.get("episode_ids_json")) if str(v).strip()]
        thread_payload["topics"] = [str(v) for v in _safe_json_list(thread_payload.get("topics_json")) if str(v).strip()]
        thread_payload["participants"] = _normalize_people(_safe_json_list(thread_payload.get("participants_json")))
        thread_payload["commitments"] = _safe_json_list(thread_payload.get("commitments_json"))
        day_threads.append(thread_payload)
        for episode_id in thread_payload["episode_ids"]:
            if episode_id not in episode_ids:
                episode_ids.append(episode_id)

    episodes: list[dict[str, Any]] = []
    for episode_id in episode_ids:
        episode_row = db.fetchone(
            """
            SELECT id, started_at, ended_at, status, summary, clean_text,
                   topics_json, participants_json, commitments_json, day_key,
                   thread_key, long_thread_key, quality_state
            FROM episodes
            WHERE id = ?
            LIMIT 1
            """,
            (episode_id,),
        )
        if not episode_row:
            continue
        episode_payload = dict(episode_row)
        episode_payload["topics"] = [str(v) for v in _safe_json_list(episode_payload.get("topics_json")) if str(v).strip()]
        episode_payload["participants"] = _normalize_people(_safe_json_list(episode_payload.get("participants_json")))
        episode_payload["commitments"] = _safe_json_list(episode_payload.get("commitments_json"))
        episodes.append(episode_payload)

    payload["day_threads"] = day_threads
    payload["episodes"] = episodes
    return payload
