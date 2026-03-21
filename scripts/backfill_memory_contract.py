"""
Memory Backbone backfill — honest re-evaluation of all structured_events.

4-pass approach:
1. Schema pass — add owner_scope/source_kind/lineage_id with NULL defaults
2. Ownership pass — populate from transcriptions.is_user
3. Truth re-eval pass — reclassify ALL events (not just uncertain)
4. Verify pass — print honest distribution

Usage:
    python scripts/backfill_memory_contract.py --mode=dry_run   # preview
    python scripts/backfill_memory_contract.py --mode=apply      # execute
"""

import argparse
import sys
from pathlib import Path

# WHY: ensure project root is on sys.path for src imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.storage.db import get_reflexio_db
from src.storage.ingest_persist import ensure_ingest_tables
from src.utils.config import settings


def get_db():
    db_path = settings.STORAGE_PATH / "reflexio.db"
    ensure_ingest_tables(db_path)
    return get_reflexio_db(db_path), db_path


def pass_1_schema(db):
    """Add missing columns with NULL defaults (not optimistic 'trusted')."""
    cols = [
        ("owner_scope", "TEXT"),
        ("source_kind", "TEXT"),
        ("lineage_id", "TEXT"),
    ]
    added = 0
    for name, typ in cols:
        try:
            db.conn.execute(f"ALTER TABLE structured_events ADD COLUMN {name} {typ}")
            added += 1
        except Exception:
            pass  # already exists
    print(f"  [pass 1] Schema: {added} columns added")


def pass_2_ownership(db, apply: bool):
    """Set owner_scope from transcriptions.is_user."""
    # Count current state
    rows = db.fetchall(
        "SELECT owner_scope, COUNT(*) as cnt FROM structured_events WHERE is_current=1 GROUP BY owner_scope"
    )
    print("  [pass 2] Before:")
    for r in rows:
        print(f"    owner_scope={r['owner_scope']}: {r['cnt']}")

    if not apply:
        # Preview what would change
        preview = db.fetchone("""
            SELECT
                SUM(CASE WHEN t.is_user = 1 THEN 1 ELSE 0 END) as self_count,
                SUM(CASE WHEN t.is_user = 0 THEN 1 ELSE 0 END) as other_count,
                SUM(CASE WHEN t.is_user IS NULL THEN 1 ELSE 0 END) as unknown_count
            FROM structured_events se
            LEFT JOIN transcriptions t ON se.transcription_id = t.id
            WHERE se.is_current = 1
        """)
        if preview:
            print(
                f"  [pass 2] Would set: self={preview['self_count']}, other={preview['other_count']}, unknown={preview['unknown_count']}"
            )
        return

    # Apply ownership from transcriptions.is_user
    db.conn.execute("""
        UPDATE structured_events SET
            owner_scope = CASE
                WHEN transcription_id IN (SELECT id FROM transcriptions WHERE is_user = 1) THEN 'self'
                WHEN transcription_id IN (SELECT id FROM transcriptions WHERE is_user = 0) THEN 'other_person'
                ELSE 'unknown'
            END,
            source_kind = 'user_speech',
            lineage_id = transcription_id
        WHERE is_current = 1
    """)
    db.conn.commit()

    # Show result
    rows = db.fetchall(
        "SELECT owner_scope, COUNT(*) as cnt FROM structured_events WHERE is_current=1 GROUP BY owner_scope"
    )
    print("  [pass 2] After:")
    for r in rows:
        print(f"    owner_scope={r['owner_scope']}: {r['cnt']}")


def pass_3_truth_reeval(db, db_path, apply: bool):
    """Reset quality_state and re-evaluate via truth layer."""
    from src.memory.truth import reclassify_episodes_for_range

    # Find date range
    bounds = db.fetchone(
        "SELECT MIN(date(created_at)) as min_d, MAX(date(created_at)) as max_d FROM structured_events WHERE is_current=1"
    )
    if not bounds or not bounds["min_d"]:
        print("  [pass 3] No events to re-evaluate")
        return

    start_day, end_day = bounds["min_d"], bounds["max_d"]
    print(f"  [pass 3] Re-evaluating {start_day} to {end_day}...")

    if apply:
        # Reset quality_state to NULL so truth layer re-evaluates honestly
        db.conn.execute("UPDATE structured_events SET quality_state = NULL WHERE is_current = 1")
        db.conn.commit()

    result = reclassify_episodes_for_range(
        db_path, start_day=start_day, end_day=end_day, apply_changes=apply
    )
    proposed = result.get("proposed_state_counts", result.get("state_counts", {}))
    print(f"  [pass 3] {'Applied' if apply else 'Proposed'}: {proposed}")
    print(f"  [pass 3] Episodes affected: {result.get('affected_episodes', '?')}")


def pass_4_verify(db):
    """Print honest distribution."""
    print("\n=== VERIFICATION ===")

    # Structured events quality
    rows = db.fetchall(
        "SELECT quality_state, COUNT(*) as cnt FROM structured_events WHERE is_current=1 GROUP BY quality_state ORDER BY quality_state"
    )
    total = sum(r["cnt"] for r in rows)
    print(f"\nStructured Events (is_current=1): {total}")
    for r in rows:
        pct = round(r["cnt"] / total * 100, 1) if total else 0
        print(f"  {r['quality_state'] or 'NULL'}: {r['cnt']} ({pct}%)")

    # Ownership breakdown
    rows = db.fetchall(
        "SELECT owner_scope, COUNT(*) as cnt FROM structured_events WHERE is_current=1 GROUP BY owner_scope ORDER BY owner_scope"
    )
    print(f"\nOwnership:")
    for r in rows:
        print(f"  {r['owner_scope'] or 'NULL'}: {r['cnt']}")

    # Episodes quality
    rows = db.fetchall(
        "SELECT quality_state, COUNT(*) as cnt FROM episodes GROUP BY quality_state ORDER BY quality_state"
    )
    ep_total = sum(r["cnt"] for r in rows)
    print(f"\nEpisodes: {ep_total}")
    for r in rows:
        print(f"  {r['quality_state'] or 'NULL'}: {r['cnt']}")

    # Transcriptions quality
    rows = db.fetchall(
        "SELECT quality_state, COUNT(*) as cnt FROM transcriptions GROUP BY quality_state ORDER BY quality_state"
    )
    tr_total = sum(r["cnt"] for r in rows)
    print(f"\nTranscriptions: {tr_total}")
    for r in rows:
        print(f"  {r['quality_state'] or 'NULL'}: {r['cnt']}")

    # Trusted fraction
    if total > 0:
        trusted = sum(
            r["cnt"]
            for r in db.fetchall(
                "SELECT COUNT(*) as cnt FROM structured_events WHERE is_current=1 AND quality_state='trusted'"
            )
        )
        print(f"\ntrusted_fraction: {round(trusted / total * 100, 1)}%")


def main():
    parser = argparse.ArgumentParser(description="Memory Backbone backfill")
    parser.add_argument("--mode", choices=["dry_run", "apply"], default="dry_run")
    args = parser.parse_args()

    apply = args.mode == "apply"
    print(f"Memory Backbone Backfill — mode={args.mode}")
    print("=" * 50)

    db, db_path = get_db()

    print("\nPass 1: Schema")
    pass_1_schema(db)

    print("\nPass 2: Ownership")
    pass_2_ownership(db, apply)

    print("\nPass 3: Truth Re-evaluation")
    pass_3_truth_reeval(db, db_path, apply)

    pass_4_verify(db)
    db.close_conn()


if __name__ == "__main__":
    main()
