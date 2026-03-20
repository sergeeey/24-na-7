"""User Profile API — view and manually correct profile knowledge.

WHY: Auto-extracted profile needs manual corrections.
"Ирина" → "Катерина" (Whisper misheard), relationship "unknown" → "жена".
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.utils.config import settings
from src.utils.logging import get_logger
from src.memory.user_profile import (
    get_profile,
    set_profile_fact,
    get_known_people,
    upsert_person,
    extract_people_from_events,
    extract_profile_facts_from_events,
    get_enrichment_context,
)

logger = get_logger("api.profile")
router = APIRouter(prefix="/profile", tags=["profile"])


@router.get("")
def get_user_profile():
    """Return full user profile."""
    db_path = settings.STORAGE_PATH / "reflexio.db"
    profile = get_profile(db_path)
    people = get_known_people(db_path)
    context = get_enrichment_context(db_path)
    return {
        "profile": profile,
        "known_people": people,
        "enrichment_context": context,
        "people_count": len(people),
    }


class ProfileFactRequest(BaseModel):
    key: str
    value: str


@router.post("/fact")
def set_fact(req: ProfileFactRequest):
    """Manually set a profile fact (e.g., user_name, work_role)."""
    db_path = settings.STORAGE_PATH / "reflexio.db"
    set_profile_fact(db_path, req.key, req.value, source="manual", confidence=1.0)
    return {"status": "ok", "key": req.key, "value": req.value}


class PersonUpdateRequest(BaseModel):
    name: str
    relationship: str = "unknown"
    context: str = ""


@router.post("/person")
def update_person(req: PersonUpdateRequest):
    """Manually set or correct a person's relationship."""
    db_path = settings.STORAGE_PATH / "reflexio.db"
    upsert_person(db_path, req.name, req.relationship, req.context, source="manual")
    return {"status": "ok", "name": req.name, "relationship": req.relationship}


@router.post("/extract")
def run_extraction(hours: int = 24):
    """Run profile extraction from recent structured events."""
    db_path = settings.STORAGE_PATH / "reflexio.db"
    people_count = extract_people_from_events(db_path, since_hours=hours)
    facts_count = extract_profile_facts_from_events(db_path, since_hours=hours)
    return {
        "status": "ok",
        "people_extracted": people_count,
        "facts_extracted": facts_count,
    }
