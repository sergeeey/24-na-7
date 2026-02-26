"""Linguistic marker extraction (LIWC-like lightweight heuristics)."""
from __future__ import annotations

ABSOLUTIST_WORDS = {"всегда", "никогда", "невозможно", "обязан", "должен"}
SELF_CRITICAL_WORDS = {"опять я", "снова не", "как всегда плохо", "я плохо"}
PROCRASTINATION_WORDS = {"потом", "завтра", "как-нибудь", "ещё успею", "еще успею"}


def _count_word_hits(text: str, lexicon: set[str]) -> int:
    lower = (text or "").lower()
    return sum(1 for token in lexicon if token in lower)


def analyze_linguistic_markers(text: str) -> dict:
    words = [w for w in (text or "").lower().split() if w.strip()]
    wc = max(len(words), 1)

    absolutism = _count_word_hits(text, ABSOLUTIST_WORDS)
    self_crit = _count_word_hits(text, SELF_CRITICAL_WORDS)
    procrastination = _count_word_hits(text, PROCRASTINATION_WORDS)

    return {
        "word_count": len(words),
        "absolutism_score": round(absolutism / wc, 4),
        "self_criticism_score": round(self_crit / wc, 4),
        "procrastination_score": round(procrastination / wc, 4),
        "signals": {
            "absolutism_hits": absolutism,
            "self_criticism_hits": self_crit,
            "procrastination_hits": procrastination,
        },
    }
