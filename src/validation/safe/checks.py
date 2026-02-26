"""Local SAFE checker compatible with middleware and ingest flows."""
from __future__ import annotations

from pathlib import Path
from typing import Any


class SAFEChecker:
    """Basic SAFE checker for payloads and file constraints."""

    ALLOWED_EXTENSIONS = {".wav", ".wave"}
    MAX_FILE_SIZE_BYTES = 25 * 1024 * 1024  # 25 MB

    def validate_payload(self, payload: dict[str, Any], require_pii_mask: bool = True) -> dict[str, Any]:
        errors: list[str] = []

        if not isinstance(payload, dict):
            errors.append("payload must be an object")
        if len(str(payload)) > 2_000_000:
            errors.append("payload too large")

        # Light guard for obvious secret leakage in payload.
        text_repr = str(payload).lower()
        if require_pii_mask and ("sk-" in text_repr or "password" in text_repr):
            errors.append("possible secret in payload")

        return {"valid": len(errors) == 0, "errors": errors}

    def check_file_extension(self, path: Path) -> tuple[bool, str]:
        suffix = (path.suffix or "").lower()
        if suffix in self.ALLOWED_EXTENSIONS:
            return True, "ok"
        return False, f"unsupported extension: {suffix or '<none>'}"

    def check_file_size(self, path: Path) -> tuple[bool, str]:
        try:
            size = path.stat().st_size
        except FileNotFoundError:
            return False, "file_not_found"

        if size <= 0:
            return False, "empty_file"
        if size > self.MAX_FILE_SIZE_BYTES:
            return False, f"file too large: {size} > {self.MAX_FILE_SIZE_BYTES}"
        return True, "ok"
