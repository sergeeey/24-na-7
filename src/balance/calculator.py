"""Shared balance calculator — single source of truth for /balance/wheel and mirror.

WHY: balance was computed independently in storage.py and mirror.py, leading to
silent divergence (mirror read non-existent table, balance used different SQL).
This module provides one calculation that both endpoints share.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from src.storage.db import ReflexioDB


@dataclass
class DomainMetrics:
    domain: str
    mentions: int
    presence_score: float  # 0.0-1.0 normalized by max mentions
    avg_sentiment: float  # -1.0 to +1.0


@dataclass
class BalanceResult:
    domains: list[DomainMetrics]
    balance_score: float  # 0.0-1.0 (1 = evenly distributed)
    total_mentions: int
    covered_domains: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "domains": [
                {
                    "domain": d.domain,
                    "mentions": d.mentions,
                    "presence_score": d.presence_score,
                    "avg_sentiment": d.avg_sentiment,
                }
                for d in self.domains
            ],
            "balance_score": self.balance_score,
            "total_mentions": self.total_mentions,
            "covered_domains": self.covered_domains,
        }

    def to_mirror_trend(self) -> list[dict[str, Any]]:
        """Format for mirror.balance_trend — backward compat with avg_score."""
        return [
            {
                "domain": d.domain,
                "avg_score": d.presence_score,
                "mentions": d.mentions,
            }
            for d in self.domains
        ]


def calculate_balance(db: ReflexioDB, date_from: str, date_to: str) -> BalanceResult:
    """Calculate domain balance from structured_events.

    Single source of truth for both /balance/wheel and mirror portrait.
    Only counts trusted, current events in the date range.
    """
    rows = db.fetchall(
        """
        SELECT json_each.value as domain,
               COUNT(*) as mention_count,
               AVG(CASE WHEN sentiment='positive' THEN 1.0
                        WHEN sentiment='negative' THEN -1.0
                        ELSE 0.0 END) as avg_sentiment
        FROM structured_events, json_each(structured_events.domains)
        WHERE is_current = 1
          AND quality_state = 'trusted'
          AND date(created_at) BETWEEN ? AND ?
        GROUP BY json_each.value
        """,
        (date_from, date_to),
    )

    if not rows:
        return BalanceResult(domains=[], balance_score=0.0, total_mentions=0, covered_domains=0)

    max_mentions = max(int(r["mention_count"]) for r in rows)
    total = 0
    domains = []

    for row in rows:
        mentions = int(row["mention_count"] or 0)
        total += mentions
        presence = round(mentions / max_mentions, 3) if max_mentions > 0 else 0.0
        domains.append(
            DomainMetrics(
                domain=row["domain"],
                mentions=mentions,
                presence_score=presence,
                avg_sentiment=round(float(row["avg_sentiment"] or 0.0), 3),
            )
        )

    domains.sort(key=lambda d: d.mentions, reverse=True)

    # Balance score: inverse of variance (1.0 = perfectly even)
    if len(domains) >= 2:
        scores = [d.presence_score for d in domains]
        avg = sum(scores) / len(scores)
        variance = sum((s - avg) ** 2 for s in scores) / len(scores)
        balance_score = round(1.0 / (1.0 + variance), 3)
    else:
        balance_score = 0.0

    return BalanceResult(
        domains=domains,
        balance_score=balance_score,
        total_mentions=total,
        covered_domains=len(domains),
    )
