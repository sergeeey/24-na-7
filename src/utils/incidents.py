"""Утилиты Incident Memory System."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

LEDGER_PATH = Path(__file__).resolve().parents[2] / "docs" / "incidents" / "ledger.yaml"
ALLOWED_INCIDENT_STATUSES = {"open", "in_progress", "closed"}
_PLACEHOLDER_PREFIXES = ("(уточнить)", "(добавить)", "todo", "tbd")


def load_incident_ledger(path: Path | None = None) -> dict[str, Any]:
    """Загружает incident ledger из YAML. Возвращает пустой dict если файл не найден."""
    ledger_path = path or LEDGER_PATH
    if not ledger_path.exists():
        return {}
    with ledger_path.open("r", encoding="utf-8") as handle:
        payload = yaml.safe_load(handle) or {}
    if not isinstance(payload, dict):
        raise ValueError("Incident ledger must be a mapping at the top level")
    return payload


def validate_incident_ledger(payload: dict[str, Any]) -> list[str]:
    """Проверяет структуру и минимальные policy-правила incident ledger."""
    incidents = payload.get("incidents")
    if not isinstance(incidents, list):
        return ["Top-level 'incidents' key must contain a list"]

    errors: list[str] = []
    seen_ids: set[str] = set()
    seen_signatures: set[str] = set()
    required_keys = {
        "incident_id",
        "signature",
        "title",
        "symptoms",
        "root_cause",
        "evidence",
        "what_worked",
        "what_failed",
        "guardrail",
        "regression_test",
        "signpost",
        "owner",
        "status",
    }

    for index, incident in enumerate(incidents, start=1):
        label = f"incidents[{index}]"
        if not isinstance(incident, dict):
            errors.append(f"{label} must be a mapping")
            continue

        missing = sorted(required_keys - set(incident))
        if missing:
            errors.append(f"{label} missing keys: {', '.join(missing)}")
            continue

        incident_id = str(incident.get("incident_id", "")).strip()
        signature = str(incident.get("signature", "")).strip()
        status = str(incident.get("status", "")).strip()

        if not incident_id:
            errors.append(f"{label}.incident_id must be non-empty")
        elif incident_id in seen_ids:
            errors.append(f"{label}.incident_id duplicates '{incident_id}'")
        else:
            seen_ids.add(incident_id)

        if not signature:
            errors.append(f"{label}.signature must be non-empty")
        elif signature in seen_signatures:
            errors.append(f"{label}.signature duplicates '{signature}'")
        else:
            seen_signatures.add(signature)

        if status not in ALLOWED_INCIDENT_STATUSES:
            errors.append(f"{label}.status must be one of {sorted(ALLOWED_INCIDENT_STATUSES)}")

        for list_key in ("symptoms", "evidence"):
            value = incident.get(list_key)
            if not isinstance(value, list) or not value:
                errors.append(f"{label}.{list_key} must be a non-empty list")

        if status == "closed":
            if not _has_meaningful_text(incident.get("root_cause")):
                errors.append(f"{label}.root_cause must be filled before status=closed")
            if not _has_meaningful_text(incident.get("signpost")):
                errors.append(f"{label}.signpost must be filled before status=closed")
            has_guard = _has_meaningful_text(incident.get("guardrail"))
            has_test = _has_meaningful_text(incident.get("regression_test"))
            if not (has_guard or has_test):
                errors.append(f"{label} requires guardrail or regression_test before status=closed")

    return errors


def build_incident_summary(payload: dict[str, Any]) -> dict[str, int]:
    """Возвращает компактную статистику по incident ledger."""
    incidents = payload.get("incidents")
    if not isinstance(incidents, list):
        return {"total": 0, "open": 0, "in_progress": 0, "closed": 0}

    summary = {"total": len(incidents), "open": 0, "in_progress": 0, "closed": 0}
    for incident in incidents:
        if not isinstance(incident, dict):
            continue
        status = str(incident.get("status", "")).strip()
        if status in summary:
            summary[status] += 1
    return summary


def _has_meaningful_text(value: Any) -> bool:
    text = str(value or "").strip()
    if not text:
        return False
    lowered = text.lower()
    return not lowered.startswith(_PLACEHOLDER_PREFIXES)
