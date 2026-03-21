"""Cascade quality/ownership from source truth (episodes/transcriptions) to derived layer (structured_events).

WHY: reclassify_episodes_for_range updates episodes and transcriptions but does NOT
propagate changes to structured_events. Without this cascade, structured_events
remain stale or NULL after truth re-evaluation.

RULE: after any reclassify, rebuild, or backfill — call cascade_quality_to_structured_events().
"""

from __future__ import annotations

import structlog
from src.storage.db import ReflexioDB

logger = structlog.get_logger(__name__)


def cascade_quality_to_structured_events(db: ReflexioDB) -> int:
    """Propagate quality_state and owner_scope from parent entities to structured_events.

    Priority: episode > transcription > fallback ('uncertain'/'unknown').

    Returns number of rows updated.
    """
    c = db.conn
    updated = 0

    # Pass 1: from episodes (primary parent)
    result = c.execute(
        "UPDATE structured_events SET "
        "quality_state = (SELECT e.quality_state FROM episodes e WHERE e.id = structured_events.episode_id) "
        "WHERE is_current = 1 AND episode_id IS NOT NULL"
    )
    updated += result.rowcount

    # Pass 2: from transcriptions (fallback when no episode)
    result = c.execute(
        "UPDATE structured_events SET "
        "quality_state = (SELECT t.quality_state FROM transcriptions t WHERE t.id = structured_events.transcription_id) "
        "WHERE is_current = 1 AND quality_state IS NULL AND episode_id IS NULL"
    )
    updated += result.rowcount

    # Pass 3: hard fallback — no NULL allowed
    result = c.execute(
        "UPDATE structured_events SET quality_state = 'uncertain' "
        "WHERE is_current = 1 AND quality_state IS NULL"
    )
    updated += result.rowcount

    # Pass 4: owner_scope fallback (if still unknown after backfill)
    result = c.execute(
        "UPDATE structured_events SET owner_scope = 'unknown' "
        "WHERE is_current = 1 AND owner_scope IS NULL"
    )
    updated += result.rowcount

    c.commit()

    logger.info(
        "truth_cascade.complete",
        updated=updated,
    )
    return updated


def verify_no_nulls(db: ReflexioDB) -> dict:
    """Check invariant: no current structured_events with NULL quality_state or owner_scope.

    Returns dict with counts. All should be 0 for healthy state.
    """
    null_quality = db.fetchone(
        "SELECT COUNT(*) as cnt FROM structured_events "
        "WHERE is_current = 1 AND quality_state IS NULL"
    )
    null_owner = db.fetchone(
        "SELECT COUNT(*) as cnt FROM structured_events WHERE is_current = 1 AND owner_scope IS NULL"
    )
    null_lineage = db.fetchone(
        "SELECT COUNT(*) as cnt FROM structured_events WHERE is_current = 1 AND lineage_id IS NULL"
    )
    return {
        "null_quality_state": null_quality["cnt"],
        "null_owner_scope": null_owner["cnt"],
        "null_lineage_id": null_lineage["cnt"],
    }
