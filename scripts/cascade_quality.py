"""Cascade quality_state from episodes/transcriptions to structured_events."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.storage.db import get_reflexio_db
from src.utils.config import settings

db = get_reflexio_db(settings.STORAGE_PATH / "reflexio.db")
c = db.conn

# From episodes
c.execute(
    "UPDATE structured_events SET quality_state = ("
    "SELECT e.quality_state FROM episodes e WHERE e.id = structured_events.episode_id"
    ") WHERE is_current = 1 AND episode_id IS NOT NULL"
)

# From transcriptions (no episode)
c.execute(
    "UPDATE structured_events SET quality_state = ("
    "SELECT t.quality_state FROM transcriptions t WHERE t.id = structured_events.transcription_id"
    ") WHERE is_current = 1 AND quality_state IS NULL AND episode_id IS NULL"
)

# Remaining NULLs
c.execute(
    "UPDATE structured_events SET quality_state = 'uncertain' WHERE is_current = 1 AND quality_state IS NULL"
)
c.commit()

# Report
rows = c.execute(
    "SELECT quality_state, COUNT(*) FROM structured_events WHERE is_current=1 GROUP BY quality_state ORDER BY quality_state"
).fetchall()
total = sum(r[1] for r in rows)
print(f"Structured Events: {total}")
for r in rows:
    print(f"  {r[0]}: {r[1]} ({round(r[1] / total * 100, 1)}%)")

rows2 = c.execute(
    "SELECT owner_scope, COUNT(*) FROM structured_events WHERE is_current=1 GROUP BY owner_scope"
).fetchall()
print("Ownership:")
for r in rows2:
    print(f"  {r[0]}: {r[1]}")

db.close_conn()
print("CASCADE COMPLETE")
