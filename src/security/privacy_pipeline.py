"""Local-first privacy pipeline for transcription text."""
from __future__ import annotations

from dataclasses import dataclass

from src.utils.guardrails import PIIDetector


@dataclass
class PrivacyResult:
    """Result of privacy processing for text payloads."""

    allowed: bool
    text: str
    mode: str
    pii_count: int
    reason: str


_PII_DETECTOR = PIIDetector()


def apply_privacy_mode(text: str, mode: str = "audit") -> PrivacyResult:
    """Apply privacy policy to text.

    Modes:
    - strict: block payload with PII
    - mask: redact PII and allow
    - audit: allow and keep original text
    """
    normalized_mode = (mode or "audit").strip().lower()
    if normalized_mode not in {"strict", "mask", "audit"}:
        normalized_mode = "audit"

    findings = _PII_DETECTOR.detect(text or "")
    pii_count = len(findings)

    if pii_count == 0:
        return PrivacyResult(
            allowed=True,
            text=text or "",
            mode=normalized_mode,
            pii_count=0,
            reason="no_pii",
        )

    if normalized_mode == "strict":
        return PrivacyResult(
            allowed=False,
            text="",
            mode=normalized_mode,
            pii_count=pii_count,
            reason="pii_blocked",
        )

    if normalized_mode == "mask":
        return PrivacyResult(
            allowed=True,
            text=_PII_DETECTOR.mask(text or ""),
            mode=normalized_mode,
            pii_count=pii_count,
            reason="pii_masked",
        )

    return PrivacyResult(
        allowed=True,
        text=text or "",
        mode=normalized_mode,
        pii_count=pii_count,
        reason="pii_detected_audit",
    )
