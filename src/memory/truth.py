"""Truth layer helpers for trusted episodic memory."""

from __future__ import annotations

import json
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.storage.db import get_reflexio_db
from src.storage.ingest_persist import QUALITY_STATES, ensure_ingest_tables
from src.utils.logging import get_logger

logger = get_logger("memory.truth")

TOKEN_RE = r"[A-Za-zА-Яа-яЁё0-9]{2,}"


def _reason(code: str, severity: str, score_delta: float, **details: Any) -> dict[str, Any]:
    return {
        "code": code,
        "severity": severity,
        "score_delta": score_delta,
        "details": details,
    }


def _tokens(text: str) -> list[str]:
    import re

    return [token.lower() for token in re.findall(TOKEN_RE, text or "")]


# WHY: TV/YouTube audio passes speaker verification because the phone mic
# picks up speaker output. Content-based detection catches what acoustic
# analysis can't — recognizable media phrases in the transcribed text.
_MEDIA_TEXT_MARKERS = [
    "субтитры",
    "подпишитесь",
    "подписывайтесь",
    "ставьте лайк",
    "спасибо за просмотр",
    "dimatorzok",
    "DimaTorzok",
    "смотрите в следующей серии",
    "не переключайтесь",
    "добро пожаловать на канал",
    "всем привет с вами",
    "ссылка в описании",
    "промокод",
]


def _is_media_content(text: str) -> bool:
    """Detect TV/YouTube content by text markers."""
    lower = (text or "").lower()
    return any(marker.lower() in lower for marker in _MEDIA_TEXT_MARKERS)


def _signature(text: str) -> str:
    tokens = _tokens(text)
    if len(tokens) < 2:
        return ""
    return " ".join(tokens[:12])


def _instability_markers(reasons: list[dict[str, Any]], score: float) -> dict[str, Any]:
    reason_codes = {reason["code"] for reason in reasons}
    return {
        "context_instability_score": round(max(0.0, 1.0 - score), 3),
        "episode_instability": "DUPLICATE_NEIGHBOR" in reason_codes
        or "REPEATED_PHRASE" in reason_codes,
        "day_context_fragility": "LOW_INFORMATION" in reason_codes
        or "EPISODE_CONTRADICTION" in reason_codes,
        "turning_point": False,
        "mode_shift": "DUPLICATE_NEIGHBOR" in reason_codes,
    }


def evaluate_transcription_truth(
    db_path: Path,
    transcription_id: str,
) -> dict[str, Any] | None:
    ensure_ingest_tables(db_path)
    db = get_reflexio_db(db_path)
    row = db.fetchone(
        """
        SELECT id, episode_id, created_at, text, transcript_clean, quality_state,
               is_user, speaker_confidence
        FROM transcriptions
        WHERE id = ?
        LIMIT 1
        """,
        (transcription_id,),
    )
    if not row:
        return None

    text = (row["transcript_clean"] or row["text"] or "").strip()
    tokens = _tokens(text)
    token_count = len(tokens)
    unique_count = len(set(tokens))
    unique_ratio = (unique_count / token_count) if token_count else 0.0
    counts = Counter(tokens)
    dominant_share = (max(counts.values()) / token_count) if token_count else 0.0
    bigrams = list(zip(tokens, tokens[1:]))
    repeated_bigram_count = max(Counter(bigrams).values(), default=0)

    reasons: list[dict[str, Any]] = []
    score = 1.0

    if token_count == 0:
        reasons.append(_reason("EMPTY_TRANSCRIPT", "high", -1.0, token_count=0))
        score = 0.0
    # WHY 2 not 4: always-on mobile recording generates many 1-3 word segments.
    # 4-token threshold was marking 70%+ as LOW_INFORMATION → uncertain.
    # 2 tokens aligns with MIN_WORDS in is_meaningful_transcription.
    elif token_count < 2 or unique_ratio < 0.3:
        reasons.append(
            _reason(
                "LOW_INFORMATION",
                "medium",
                -0.25,
                token_count=token_count,
                unique_tokens=unique_count,
                unique_ratio=round(unique_ratio, 3),
            )
        )
        score -= 0.35

    repeated_phrase = token_count >= 5 and (dominant_share >= 0.45 or repeated_bigram_count >= 2)
    if repeated_phrase:
        reasons.append(
            _reason(
                "REPEATED_PHRASE",
                "high",
                -0.45,
                dominant_share=round(dominant_share, 3),
                repeated_bigram_count=repeated_bigram_count,
            )
        )
        score -= 0.45

    duplicate_neighbors = 0
    signature = _signature(text)
    if signature and row["created_at"]:
        recent_rows = db.fetchall(
            """
            SELECT id, text, transcript_clean
            FROM transcriptions
            WHERE id != ?
              AND created_at >= datetime(?, '-30 minutes')
              AND created_at <= datetime(?, '+30 minutes')
            ORDER BY created_at DESC
            LIMIT 12
            """,
            (transcription_id, row["created_at"], row["created_at"]),
        )
        for recent in recent_rows:
            if _signature(recent["transcript_clean"] or recent["text"] or "") == signature:
                duplicate_neighbors += 1
    low_information_duplicate = (
        dominant_share >= 0.5 or unique_ratio <= 0.55 or unique_count <= 3 or token_count <= 5
    )
    if duplicate_neighbors >= 1 and low_information_duplicate:
        reasons.append(
            _reason(
                "DUPLICATE_NEIGHBOR",
                "high",
                -0.3,
                duplicate_neighbors=duplicate_neighbors,
            )
        )
        score -= 0.3

    contradiction = bool(repeated_phrase and duplicate_neighbors >= 2 and low_information_duplicate)
    if contradiction:
        reasons.append(
            _reason(
                "TRANSCRIPT_CONTRADICTION",
                "medium",
                -0.15,
                duplicate_neighbors=duplicate_neighbors,
            )
        )
        score -= 0.15

    # WHY: content-based media detection catches TV/YouTube that passes speaker verification.
    if _is_media_content(text):
        reasons.append(_reason("MEDIA_CONTENT_DETECTED", "high", -0.5, text_snippet=text[:60]))
        score -= 0.5

    # WHY: ownership-aware quality — non-user speech should not be treated as trusted memory.
    # is_user=0 means speaker verification determined this is background/TV/other person.
    is_user = row["is_user"]
    speaker_conf = row["speaker_confidence"] or 0.0
    if is_user is not None and not is_user:
        reasons.append(
            _reason(
                "NON_USER_SPEAKER",
                "high",
                -0.4,
                is_user=False,
                speaker_confidence=round(speaker_conf, 3),
            )
        )
        score -= 0.4
    elif is_user is not None and is_user and speaker_conf < 0.3:
        reasons.append(
            _reason(
                "LOW_SPEAKER_CONFIDENCE",
                "low",
                -0.1,
                speaker_confidence=round(speaker_conf, 3),
            )
        )
        score -= 0.1

    score = max(0.0, min(1.0, score))
    if contradiction and duplicate_neighbors >= 2:
        quality_state = "quarantined"
    elif token_count == 0:
        quality_state = "garbage"
    elif repeated_phrase and (
        (duplicate_neighbors >= 1 and low_information_duplicate) or dominant_share >= 0.55
    ):
        quality_state = "garbage"
    elif score < 0.72 or repeated_phrase:
        quality_state = "uncertain"
    else:
        quality_state = "trusted"

    return {
        "quality_state": quality_state if quality_state in QUALITY_STATES else "uncertain",
        "quality_score": round(score, 3),
        "quality_reasons_json": reasons,
        "review_required": quality_state != "trusted",
        "needs_recheck": quality_state != "trusted",
        "instability_markers": _instability_markers(reasons, score),
        "evidence_strength": round(score, 3),
    }


def evaluate_episode_truth(db_path: Path, episode_id: str) -> dict[str, Any] | None:
    ensure_ingest_tables(db_path)
    db = get_reflexio_db(db_path)
    row = db.fetchone(
        """
        SELECT id, day_key, started_at, ended_at, source_count, clean_text, raw_text,
               topics_json, participants_json, commitments_json
        FROM episodes
        WHERE id = ?
        LIMIT 1
        """,
        (episode_id,),
    )
    if not row:
        return None

    text = (row["clean_text"] or row["raw_text"] or "").strip()
    tokens = _tokens(text)
    token_count = len(tokens)
    unique_count = len(set(tokens))
    unique_ratio = (unique_count / token_count) if token_count else 0.0
    counts = Counter(tokens)
    dominant_share = (max(counts.values()) / token_count) if token_count else 0.0
    bigrams = list(zip(tokens, tokens[1:]))
    repeated_bigram_count = max(Counter(bigrams).values(), default=0)
    source_count = int(row["source_count"] or 0)

    reasons: list[dict[str, Any]] = []
    score = 1.0

    # WHY 2 not 4: aligned with evaluate_transcription_truth.
    # 4-token threshold was marking short but valid commands ("купи хлеб")
    # as LOW_INFORMATION → uncertain, causing trusted_fraction=15.8%.
    if token_count < 2 or unique_ratio < 0.3:
        reasons.append(
            _reason(
                "LOW_INFORMATION",
                "medium",
                -0.25,
                token_count=token_count,
                unique_tokens=unique_count,
                unique_ratio=round(unique_ratio, 3),
            )
        )
        score -= 0.25

    repeated_phrase = token_count >= 5 and (dominant_share >= 0.45 or repeated_bigram_count >= 2)
    if repeated_phrase:
        reasons.append(
            _reason(
                "REPEATED_PHRASE",
                "high",
                -0.45,
                dominant_share=round(dominant_share, 3),
                repeated_bigram_count=repeated_bigram_count,
            )
        )
        score -= 0.45

    signature = _signature(text)
    duplicate_neighbors = 0
    if signature:
        recent_rows = db.fetchall(
            """
            SELECT id, clean_text, raw_text
            FROM episodes
            WHERE day_key = ? AND id != ? AND started_at >= datetime(?, '-30 minutes')
            ORDER BY started_at DESC
            LIMIT 8
            """,
            (row["day_key"], episode_id, row["started_at"]),
        )
        for recent in recent_rows:
            if _signature(recent["clean_text"] or recent["raw_text"] or "") == signature:
                duplicate_neighbors += 1
    low_information_duplicate = (
        dominant_share >= 0.5 or unique_ratio <= 0.55 or unique_count <= 3 or token_count <= 5
    )
    if duplicate_neighbors >= 1 and low_information_duplicate:
        reasons.append(
            _reason(
                "DUPLICATE_NEIGHBOR",
                "high",
                -0.3,
                duplicate_neighbors=duplicate_neighbors,
            )
        )
        score -= 0.3

    topics = json.loads(row["topics_json"] or "[]")
    participants = json.loads(row["participants_json"] or "[]")
    contradiction = bool(token_count >= 6 and not topics and not participants and repeated_phrase)
    if contradiction:
        reasons.append(
            _reason(
                "EPISODE_CONTRADICTION",
                "medium",
                -0.15,
                topics=0,
                participants=0,
                repeated_phrase=repeated_phrase,
            )
        )
        score -= 0.15

    # WHY: ownership-aware episode quality — check speaker composition of child transcriptions.
    # Episodes dominated by background speakers (TV, reels) should not be trusted memory.
    child_rows = db.fetchall(
        "SELECT is_user, speaker_confidence FROM transcriptions WHERE episode_id = ?",
        (episode_id,),
    )
    if child_rows:
        user_count = sum(1 for r in child_rows if r["is_user"])
        total_children = len(child_rows)
        user_ratio = user_count / total_children if total_children else 0.5
        avg_confidence = sum(r["speaker_confidence"] or 0.0 for r in child_rows) / total_children
        if user_count == 0 and total_children > 0:
            reasons.append(
                _reason("ALL_BACKGROUND", "high", -0.5, user_ratio=0.0, children=total_children)
            )
            score -= 0.5
        elif user_ratio < 0.5 and total_children >= 2:
            reasons.append(
                _reason(
                    "MIXED_OWNERSHIP",
                    "medium",
                    -0.15,
                    user_ratio=round(user_ratio, 2),
                    children=total_children,
                )
            )
            score -= 0.15
        if avg_confidence < 0.3 and avg_confidence > 0.0:
            reasons.append(
                _reason(
                    "LOW_SPEAKER_CONFIDENCE", "low", -0.1, avg_confidence=round(avg_confidence, 3)
                )
            )
            score -= 0.1

    score = max(0.0, min(1.0, score))
    if contradiction and duplicate_neighbors >= 1 and low_information_duplicate:
        quality_state = "quarantined"
    elif token_count == 0:
        quality_state = "garbage"
    elif repeated_phrase and (
        (duplicate_neighbors >= 1 and low_information_duplicate) or dominant_share >= 0.55
    ):
        quality_state = "garbage"
    elif score < 0.72 or contradiction or repeated_phrase:
        quality_state = "uncertain"
    else:
        quality_state = "trusted"

    review_required = quality_state != "trusted"
    evidence_strength = round(max(0.0, min(1.0, score * (1.0 + min(source_count, 3) * 0.1))), 3)
    markers = _instability_markers(reasons, score)
    return {
        "quality_state": quality_state if quality_state in QUALITY_STATES else "uncertain",
        "quality_score": round(score, 3),
        "quality_reasons_json": reasons,
        "review_required": review_required,
        "needs_recheck": quality_state != "trusted",
        "instability_markers": markers,
        "evidence_strength": evidence_strength,
    }


def _reason_codes(reasons: list[dict[str, Any]]) -> list[str]:
    return [str(reason.get("code")) for reason in reasons if reason.get("code")]


def _log_transition(
    db,
    *,
    entity_type: str,
    entity_id: str,
    old_state: str | None,
    new_state: str,
    reasons: list[dict[str, Any]],
    source: str,
) -> None:
    if old_state == new_state:
        return
    reason_codes = _reason_codes(reasons)
    db.execute(
        """
        INSERT INTO quality_state_transition_log (
            id, entity_type, entity_id, old_state, new_state,
            reason_codes_json, source, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            str(uuid.uuid4()),
            entity_type,
            entity_id,
            old_state,
            new_state,
            json.dumps(reason_codes),
            source,
            datetime.now(timezone.utc).isoformat(),
        ),
    )
    logger.info(
        "quality_state_transition",
        entity_type=entity_type,
        entity_id=entity_id,
        old_state=old_state,
        new_state=new_state,
        source=source,
        reason_codes=reason_codes,
    )


def apply_episode_truth_state(
    db_path: Path,
    episode_id: str,
    truth: dict[str, Any],
    *,
    source: str = "gate",
) -> dict[str, Any]:
    ensure_ingest_tables(db_path)
    db = get_reflexio_db(db_path)
    reasons = truth.get("quality_reasons_json") or []
    with db.transaction():
        episode = db.fetchone(
            "SELECT quality_state, transcription_ids_json FROM episodes WHERE id = ?",
            (episode_id,),
        )
        if not episode:
            return truth
        new_state = truth["quality_state"]
        review_required = 1 if truth.get("review_required") else 0
        needs_recheck = 1 if truth.get("needs_recheck") else 0
        db.execute(
            """
            UPDATE episodes
            SET quality_state = ?, quality_score = ?, quality_reasons_json = ?,
                review_required = ?, needs_review = ?, importance_score = MAX(COALESCE(importance_score, 0), ?)
            WHERE id = ?
            """,
            (
                new_state,
                truth.get("quality_score"),
                json.dumps(reasons),
                review_required,
                needs_recheck,
                truth.get("evidence_strength", truth.get("quality_score", 0.0)),
                episode_id,
            ),
        )
        _log_transition(
            db,
            entity_type="episode",
            entity_id=episode_id,
            old_state=episode["quality_state"],
            new_state=new_state,
            reasons=reasons,
            source=source,
        )
        transcription_ids = json.loads(episode["transcription_ids_json"] or "[]")
        for transcription_id in transcription_ids:
            current = db.fetchone(
                "SELECT quality_state FROM transcriptions WHERE id = ?",
                (transcription_id,),
            )
            if not current:
                continue
            db.execute(
                """
                UPDATE transcriptions
                SET quality_state = ?, quality_score = ?, quality_reasons_json = ?,
                    review_required = ?, needs_recheck = ?, garbage_flag = ?
                WHERE id = ?
                """,
                (
                    new_state,
                    truth.get("quality_score"),
                    json.dumps(reasons),
                    review_required,
                    needs_recheck,
                    1 if new_state in {"garbage", "quarantined"} else 0,
                    transcription_id,
                ),
            )
            _log_transition(
                db,
                entity_type="transcription",
                entity_id=transcription_id,
                old_state=current["quality_state"],
                new_state=new_state,
                reasons=reasons,
                source=source,
            )
    return truth


def apply_transcription_truth_state(
    db_path: Path,
    transcription_id: str,
    truth: dict[str, Any],
    *,
    source: str = "gate",
) -> dict[str, Any]:
    ensure_ingest_tables(db_path)
    db = get_reflexio_db(db_path)
    reasons = truth.get("quality_reasons_json") or []
    with db.transaction():
        current = db.fetchone(
            "SELECT quality_state FROM transcriptions WHERE id = ?",
            (transcription_id,),
        )
        if not current:
            return truth
        new_state = truth["quality_state"]
        review_required = 1 if truth.get("review_required") else 0
        needs_recheck = 1 if truth.get("needs_recheck") else 0
        db.execute(
            """
            UPDATE transcriptions
            SET quality_state = ?, quality_score = ?, quality_reasons_json = ?,
                review_required = ?, needs_recheck = ?, garbage_flag = ?
            WHERE id = ?
            """,
            (
                new_state,
                truth.get("quality_score"),
                json.dumps(reasons),
                review_required,
                needs_recheck,
                1 if new_state in {"garbage", "quarantined"} else 0,
                transcription_id,
            ),
        )
        _log_transition(
            db,
            entity_type="transcription",
            entity_id=transcription_id,
            old_state=current["quality_state"],
            new_state=new_state,
            reasons=reasons,
            source=source,
        )
    return truth


def get_quality_counts(db_path: Path) -> dict[str, int]:
    ensure_ingest_tables(db_path)
    db = get_reflexio_db(db_path)
    counts = {state: 0 for state in QUALITY_STATES}
    rows = db.fetchall(
        "SELECT quality_state, COUNT(*) AS count FROM episodes GROUP BY quality_state"
    )
    for row in rows:
        state = row["quality_state"] or "trusted"
        if state in counts:
            counts[state] = int(row["count"] or 0)
    return counts


def reclassify_episodes_for_range(
    db_path: Path,
    *,
    start_day: str,
    end_day: str,
    apply_changes: bool,
) -> dict[str, Any]:
    ensure_ingest_tables(db_path)
    db = get_reflexio_db(db_path)
    rows = db.fetchall(
        """
        SELECT id, day_key, quality_state
        FROM episodes
        WHERE day_key BETWEEN ? AND ?
        ORDER BY day_key ASC, started_at ASC
        """,
        (start_day, end_day),
    )
    proposals: list[dict[str, Any]] = []
    transcription_proposals: list[dict[str, Any]] = []
    affected_days: set[str] = set()
    changed_episode_ids: set[str] = set()
    for row in rows:
        truth = evaluate_episode_truth(db_path, row["id"])
        if not truth:
            continue
        proposals.append(
            {
                "episode_id": row["id"],
                "day_key": row["day_key"],
                "old_state": row["quality_state"] or "trusted",
                "new_state": truth["quality_state"],
                "reason_codes": _reason_codes(truth["quality_reasons_json"]),
            }
        )
        if (row["quality_state"] or "trusted") != truth["quality_state"]:
            affected_days.add(row["day_key"])
            changed_episode_ids.add(row["id"])
            if apply_changes:
                apply_episode_truth_state(db_path, row["id"], truth, source="reclassify")

    transcription_rows = db.fetchall(
        """
        SELECT t.id, t.episode_id, t.created_at, t.quality_state,
               COALESCE(date(t.created_at), '') AS day_key
        FROM transcriptions t
        LEFT JOIN episodes e ON t.episode_id = e.id
        WHERE date(t.created_at) BETWEEN ? AND ?
          AND (
              t.episode_id IS NULL
              OR e.id IS NULL
              OR e.status != 'summarized'
              OR COALESCE(e.quality_state, 'trusted') != 'trusted'
          )
        ORDER BY t.created_at ASC
        """,
        (start_day, end_day),
    )
    for row in transcription_rows:
        truth = evaluate_transcription_truth(db_path, row["id"])
        if not truth:
            continue
        transcription_proposals.append(
            {
                "transcription_id": row["id"],
                "episode_id": row["episode_id"],
                "day_key": row["day_key"],
                "old_state": row["quality_state"] or "trusted",
                "new_state": truth["quality_state"],
                "reason_codes": _reason_codes(truth["quality_reasons_json"]),
            }
        )
        if (row["quality_state"] or "trusted") != truth["quality_state"]:
            if row["day_key"]:
                affected_days.add(row["day_key"])
            if apply_changes:
                apply_transcription_truth_state(db_path, row["id"], truth, source="reclassify")
    return {
        "episodes": proposals,
        "transcriptions": transcription_proposals,
        "affected_days": sorted(affected_days),
        "state_counts": {
            state: sum(1 for proposal in proposals if proposal["new_state"] == state)
            for state in QUALITY_STATES
        },
        "transcription_state_counts": {
            state: sum(1 for proposal in transcription_proposals if proposal["new_state"] == state)
            for state in QUALITY_STATES
        },
        "changed_episode_count": len(changed_episode_ids),
        "changed_transcription_count": sum(
            1
            for proposal in transcription_proposals
            if proposal["old_state"] != proposal["new_state"]
        ),
    }


def recheck_non_trusted_for_range(
    db_path: Path,
    *,
    start_day: str,
    end_day: str,
    apply_changes: bool,
    target_states: tuple[str, ...] = ("uncertain", "quarantined"),
) -> dict[str, Any]:
    """Selective second-pass for already non-trusted items."""
    ensure_ingest_tables(db_path)
    db = get_reflexio_db(db_path)
    allowed_states = tuple(
        state for state in target_states if state in QUALITY_STATES and state != "trusted"
    )
    if not allowed_states:
        allowed_states = ("uncertain", "quarantined")
    state_placeholders = ",".join("?" for _ in allowed_states)

    episode_rows = db.fetchall(
        f"""
        SELECT id, day_key, quality_state
        FROM episodes
        WHERE day_key BETWEEN ? AND ?
          AND quality_state IN ({state_placeholders})
        ORDER BY day_key ASC, started_at ASC
        """,
        (start_day, end_day, *allowed_states),
    )
    proposals: list[dict[str, Any]] = []
    transcription_proposals: list[dict[str, Any]] = []
    affected_days: set[str] = set()
    changed_episode_ids: set[str] = set()
    for row in episode_rows:
        truth = evaluate_episode_truth(db_path, row["id"])
        if not truth:
            continue
        proposals.append(
            {
                "episode_id": row["id"],
                "day_key": row["day_key"],
                "old_state": row["quality_state"] or "trusted",
                "new_state": truth["quality_state"],
                "reason_codes": _reason_codes(truth["quality_reasons_json"]),
            }
        )
        if (row["quality_state"] or "trusted") != truth["quality_state"]:
            affected_days.add(row["day_key"])
            changed_episode_ids.add(row["id"])
            if apply_changes:
                apply_episode_truth_state(db_path, row["id"], truth, source="recheck")

    transcription_rows = db.fetchall(
        f"""
        SELECT t.id, t.episode_id, t.created_at, t.quality_state,
               COALESCE(date(t.created_at), '') AS day_key
        FROM transcriptions t
        LEFT JOIN episodes e ON t.episode_id = e.id
        WHERE date(t.created_at) BETWEEN ? AND ?
          AND t.quality_state IN ({state_placeholders})
          AND (
              t.episode_id IS NULL
              OR e.id IS NULL
              OR e.status != 'summarized'
              OR COALESCE(e.quality_state, 'trusted') != 'trusted'
          )
        ORDER BY t.created_at ASC
        """,
        (start_day, end_day, *allowed_states),
    )
    for row in transcription_rows:
        truth = evaluate_transcription_truth(db_path, row["id"])
        if not truth:
            continue
        transcription_proposals.append(
            {
                "transcription_id": row["id"],
                "episode_id": row["episode_id"],
                "day_key": row["day_key"],
                "old_state": row["quality_state"] or "trusted",
                "new_state": truth["quality_state"],
                "reason_codes": _reason_codes(truth["quality_reasons_json"]),
            }
        )
        if (row["quality_state"] or "trusted") != truth["quality_state"]:
            if row["day_key"]:
                affected_days.add(row["day_key"])
            if apply_changes:
                apply_transcription_truth_state(db_path, row["id"], truth, source="recheck")

    return {
        "episodes": proposals,
        "transcriptions": transcription_proposals,
        "affected_days": sorted(affected_days),
        "state_counts": {
            state: sum(1 for proposal in proposals if proposal["new_state"] == state)
            for state in QUALITY_STATES
        },
        "transcription_state_counts": {
            state: sum(1 for proposal in transcription_proposals if proposal["new_state"] == state)
            for state in QUALITY_STATES
        },
        "changed_episode_count": len(changed_episode_ids),
        "changed_transcription_count": sum(
            1
            for proposal in transcription_proposals
            if proposal["old_state"] != proposal["new_state"]
        ),
    }
