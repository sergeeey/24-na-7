#!/usr/bin/env python3
"""
Baseline Metrics Measurement for Reflexio 24/7 v4

Analyzes current digest quality to establish baseline before fact-grounded implementation:
- Hallucination rate (estimated)
- Citation coverage (how many claims have source attribution)
- Average confidence scores
- Fact extraction quality

Usage:
    python scripts/measure_baseline.py --sample-size 50
    python scripts/measure_baseline.py --date 2026-02-17
    python scripts/measure_baseline.py --output-file baseline_report.md
"""

import argparse
import json
import sqlite3
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional
import random

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.utils.config import settings
from src.utils.logging import setup_logging, get_logger
from src.digest.generator import DigestGenerator

setup_logging()
logger = get_logger("baseline")


class BaselineMetrics:
    """Calculate baseline metrics for v4 comparison."""

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or settings.STORAGE_PATH / "reflexio.db"
        self.generator = DigestGenerator(self.db_path)

    def get_sample_transcriptions(
        self,
        sample_size: int = 50,
        days_back: int = 30
    ) -> List[Dict]:
        """Get random sample of transcriptions from past N days."""
        if not self.db_path.exists():
            logger.error("database_not_found", db_path=str(self.db_path))
            return []

        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row

        try:
            cursor = conn.cursor()

            # Get all transcriptions from past N days
            cutoff_date = (datetime.now() - timedelta(days=days_back)).date()

            cursor.execute("""
                SELECT
                    t.id,
                    t.text,
                    t.created_at,
                    t.duration
                FROM transcriptions t
                WHERE DATE(t.created_at) >= ?
                  AND LENGTH(t.text) > 100
                ORDER BY t.created_at DESC
            """, (cutoff_date.isoformat(),))

            rows = cursor.fetchall()
            all_transcriptions = [dict(row) for row in rows]

            logger.info(
                "transcriptions_found",
                total=len(all_transcriptions),
                sample_size=sample_size
            )

            # Random sample
            if len(all_transcriptions) > sample_size:
                sample = random.sample(all_transcriptions, sample_size)
            else:
                sample = all_transcriptions

            return sample

        finally:
            conn.close()

    def estimate_hallucination_rate(
        self,
        transcription: Dict,
        extracted_facts: List[str]
    ) -> float:
        """
        Estimate hallucination rate by checking if facts appear in source.

        Simple heuristic: If fact text not substring of transcription → potential hallucination.
        Note: This is approximate - some paraphrasing is valid.
        """
        if not extracted_facts:
            return 0.0

        text_lower = transcription["text"].lower()
        hallucinations = 0

        for fact in extracted_facts:
            fact_lower = fact.lower()

            # Extract key words from fact (ignore stop words)
            key_words = [
                word for word in fact_lower.split()
                if len(word) > 3 and word not in ["that", "this", "with", "from"]
            ]

            # Check if at least 50% of key words appear in source
            if not key_words:
                continue

            matches = sum(1 for word in key_words if word in text_lower)
            match_ratio = matches / len(key_words)

            if match_ratio < 0.5:
                hallucinations += 1
                logger.debug(
                    "potential_hallucination",
                    fact=fact,
                    match_ratio=match_ratio
                )

        return hallucinations / len(extracted_facts)

    def calculate_citation_coverage(
        self,
        extracted_facts: List[str]
    ) -> float:
        """
        Calculate what % of facts have any form of citation/source attribution.

        Currently: 0% (no citation system exists)
        """
        # v3 has no citation system
        return 0.0

    def analyze_sample(
        self,
        transcriptions: List[Dict]
    ) -> Dict:
        """Analyze sample and calculate aggregate metrics."""
        results = {
            "total_transcriptions": len(transcriptions),
            "total_facts_extracted": 0,
            "hallucination_rates": [],
            "citation_coverage": [],
            "avg_facts_per_transcription": 0.0,
            "transcriptions_analyzed": 0,
        }

        for trans in transcriptions:
            try:
                # Extract facts using current system (basic fact extraction)
                facts = self.generator.extract_facts([trans], use_llm=False)

                if not facts:
                    continue

                # Extract fact texts
                fact_texts = [
                    f.get("fact", "") for f in facts
                    if isinstance(f, dict) and "fact" in f
                ]

                if not fact_texts:
                    continue

                results["total_facts_extracted"] += len(fact_texts)
                results["transcriptions_analyzed"] += 1

                # Estimate hallucination rate
                hallucination_rate = self.estimate_hallucination_rate(
                    trans, fact_texts
                )
                results["hallucination_rates"].append(hallucination_rate)

                # Citation coverage (always 0 in v3)
                citation_cov = self.calculate_citation_coverage(fact_texts)
                results["citation_coverage"].append(citation_cov)

                logger.debug(
                    "transcription_analyzed",
                    id=trans["id"],
                    facts_count=len(fact_texts),
                    hallucination_rate=hallucination_rate
                )

            except Exception as e:
                logger.warning(
                    "transcription_analysis_failed",
                    id=trans.get("id"),
                    error=str(e)
                )

        # Calculate aggregates
        if results["transcriptions_analyzed"] > 0:
            results["avg_facts_per_transcription"] = (
                results["total_facts_extracted"] / results["transcriptions_analyzed"]
            )

            results["avg_hallucination_rate"] = (
                sum(results["hallucination_rates"]) / len(results["hallucination_rates"])
                if results["hallucination_rates"] else 0.0
            )

            results["avg_citation_coverage"] = (
                sum(results["citation_coverage"]) / len(results["citation_coverage"])
                if results["citation_coverage"] else 0.0
            )
        else:
            results["avg_hallucination_rate"] = 0.0
            results["avg_citation_coverage"] = 0.0

        return results

    def generate_report(
        self,
        results: Dict,
        output_file: Optional[Path] = None
    ) -> str:
        """Generate markdown report."""
        report = f"""# Reflexio 24/7 Baseline Metrics Report

**Generated:** {datetime.now().isoformat()}
**Database:** {self.db_path}

## Summary

| Metric | Value | v4 Target |
|--------|-------|-----------|
| **Hallucination Rate** | {results['avg_hallucination_rate']:.2%} | ≤0.5% |
| **Citation Coverage** | {results['avg_citation_coverage']:.2%} | ≥98% |
| **Avg Facts/Transcription** | {results['avg_facts_per_transcription']:.1f} | - |

## Details

- **Total Transcriptions Sampled:** {results['total_transcriptions']}
- **Transcriptions Analyzed:** {results['transcriptions_analyzed']}
- **Total Facts Extracted:** {results['total_facts_extracted']}

## Hallucination Analysis

**Estimated Hallucination Rate:** {results['avg_hallucination_rate']:.2%}

*Note:* This is a conservative estimate using keyword matching. Actual hallucination rate may be higher as it doesn't detect:
- Paraphrasing that changes meaning
- Invented entities that sound plausible
- Temporal/causal claims without evidence

**Distribution:**
"""

        if results["hallucination_rates"]:
            # Histogram bins
            bins = [0.0, 0.01, 0.05, 0.10, 0.20, 1.0]
            bin_labels = ["<1%", "1-5%", "5-10%", "10-20%", ">20%"]
            bin_counts = [0] * len(bin_labels)

            for rate in results["hallucination_rates"]:
                for i, bin_max in enumerate(bins[1:]):
                    if rate < bin_max:
                        bin_counts[i] += 1
                        break

            for label, count in zip(bin_labels, bin_counts):
                pct = (count / len(results["hallucination_rates"])) * 100
                report += f"\n- **{label}:** {count} transcriptions ({pct:.1f}%)"

        report += f"""

## Citation Coverage

**Current Coverage:** {results['avg_citation_coverage']:.2%}

*Explanation:* v3 (current version) has **no citation system**. Facts are extracted but not linked to source text spans. This is why coverage is 0%.

**v4 Goal:** Every fact must have:
- `source_span` with character offsets in transcription
- `confidence_score` based on source grounding
- Version tag (`fact_version = "1.0"`)

## Recommendations for v4

1. **Focus on Hallucination Reduction**
   - Current: ~{results['avg_hallucination_rate']:.1%}
   - Target: ≤0.5%
   - Strategy: CoVe (Chain-of-Verification) pipeline

2. **Implement Source Attribution**
   - Current: 0% facts have citations
   - Target: 98% citation coverage
   - Strategy: SourceSpan extraction + grounding validation

3. **Golden Set Test Cases**
   - Create 20 baseline cases from analyzed transcriptions
   - Include both clean (0% hallucination) and problematic cases
   - Template generation for 30+ additional cases

## Next Steps

1. Run fact extraction on full dataset (not just sample)
2. Manual review of high-hallucination transcriptions
3. Create golden test cases from this baseline
4. Begin M1 implementation (Pydantic schemas + validators)

---

*Generated by: scripts/measure_baseline.py*
"""

        if output_file:
            output_file.write_text(report)
            logger.info("report_saved", path=str(output_file))

        return report


def main():
    parser = argparse.ArgumentParser(
        description="Measure baseline metrics for Reflexio 24/7 v4"
    )
    parser.add_argument(
        "--sample-size",
        type=int,
        default=50,
        help="Number of transcriptions to sample (default: 50)"
    )
    parser.add_argument(
        "--days-back",
        type=int,
        default=30,
        help="Look back N days for transcriptions (default: 30)"
    )
    parser.add_argument(
        "--output-file",
        type=Path,
        default=None,
        help="Output file for report (default: print to stdout)"
    )
    parser.add_argument(
        "--db-path",
        type=Path,
        default=None,
        help="Path to SQLite database (default: from settings)"
    )

    args = parser.parse_args()

    logger.info(
        "baseline_measurement_started",
        sample_size=args.sample_size,
        days_back=args.days_back
    )

    # Initialize
    metrics = BaselineMetrics(db_path=args.db_path)

    # Get sample
    transcriptions = metrics.get_sample_transcriptions(
        sample_size=args.sample_size,
        days_back=args.days_back
    )

    if not transcriptions:
        logger.error("no_transcriptions_found")
        print("❌ No transcriptions found. Check database path and date range.")
        return 1

    # Analyze
    logger.info("analyzing_sample", count=len(transcriptions))
    results = metrics.analyze_sample(transcriptions)

    # Generate report
    report = metrics.generate_report(results, output_file=args.output_file)

    # Print to stdout if no output file
    if not args.output_file:
        print(report)

    # Summary
    logger.info(
        "baseline_measurement_complete",
        hallucination_rate=results["avg_hallucination_rate"],
        citation_coverage=results["avg_citation_coverage"],
        facts_analyzed=results["total_facts_extracted"]
    )

    print(f"\n✅ Baseline measurement complete!")
    print(f"   Hallucination Rate: {results['avg_hallucination_rate']:.2%}")
    print(f"   Citation Coverage: {results['avg_citation_coverage']:.2%}")
    print(f"   Facts Analyzed: {results['total_facts_extracted']}")

    if args.output_file:
        print(f"   Report saved to: {args.output_file}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
