"""
Test fixtures for fact-grounded digest testing.

Provides reusable sample data for:
- Transcriptions (clean, noisy, multi-speaker)
- Facts (atomic, compound, vague, hallucinated)
- Source spans (exact, fuzzy, missing)
- Verification scenarios (PASS, NEEDS_REVISION, REJECT)

Usage:
    from tests.fixtures.fact_samples import SAMPLE_TRANSCRIPTIONS, SAMPLE_FACTS

    def test_fact_extraction(sample_transcription):
        # Use pre-built samples
        assert sample_transcription["text"] is not None
"""

from datetime import datetime, timedelta
from typing import Dict, List
import uuid


# ============================================================================
# TRANSCRIPTION SAMPLES
# ============================================================================

SAMPLE_TRANSCRIPTIONS = {
    "simple_medical": {
        "id": "trans_001",
        "text": "Hi, my name is John Smith. I've had a headache for two days. "
                "It started on Monday morning. I took ibuprofen but it didn't help.",
        "created_at": datetime.now().isoformat(),
        "duration": 12.5,
        "language": "en",
        "segments": [
            {"text": "Hi, my name is John Smith.", "start": 0.0, "end": 2.1},
            {"text": "I've had a headache for two days.", "start": 2.1, "end": 4.8},
            {"text": "It started on Monday morning.", "start": 4.8, "end": 7.2},
            {"text": "I took ibuprofen but it didn't help.", "start": 7.2, "end": 10.5},
        ],
    },

    "compound_claims": {
        "id": "trans_002",
        "text": "I have back pain and nausea. My temperature is 38.5. "
                "I also feel dizzy when I stand up.",
        "created_at": datetime.now().isoformat(),
        "duration": 8.0,
        "language": "en",
        "segments": [
            {"text": "I have back pain and nausea.", "start": 0.0, "end": 2.5},
            {"text": "My temperature is 38.5.", "start": 2.5, "end": 4.8},
            {"text": "I also feel dizzy when I stand up.", "start": 4.8, "end": 8.0},
        ],
    },

    "temporal_sequence": {
        "id": "trans_003",
        "text": "Yesterday I felt fine. This morning I woke up with a sore throat. "
                "By afternoon it got worse. I took some medicine around 3 PM.",
        "created_at": datetime.now().isoformat(),
        "duration": 15.0,
        "language": "en",
        "segments": [
            {"text": "Yesterday I felt fine.", "start": 0.0, "end": 2.0},
            {"text": "This morning I woke up with a sore throat.", "start": 2.0, "end": 5.5},
            {"text": "By afternoon it got worse.", "start": 5.5, "end": 8.0},
            {"text": "I took some medicine around 3 PM.", "start": 8.0, "end": 11.5},
        ],
    },

    "ambiguous_pronouns": {
        "id": "trans_004",
        "text": "My doctor prescribed medication. She said it should help. "
                "I picked it up from the pharmacy. They were very helpful.",
        "created_at": datetime.now().isoformat(),
        "duration": 10.0,
        "language": "en",
        "segments": [
            {"text": "My doctor prescribed medication.", "start": 0.0, "end": 2.5},
            {"text": "She said it should help.", "start": 2.5, "end": 4.5},
            {"text": "I picked it up from the pharmacy.", "start": 4.5, "end": 7.0},
            {"text": "They were very helpful.", "start": 7.0, "end": 9.5},
        ],
    },

    "negation_case": {
        "id": "trans_005",
        "text": "I don't have a fever. I haven't taken any medication. "
                "The pain is not severe, just annoying.",
        "created_at": datetime.now().isoformat(),
        "duration": 8.0,
        "language": "en",
        "segments": [
            {"text": "I don't have a fever.", "start": 0.0, "end": 2.0},
            {"text": "I haven't taken any medication.", "start": 2.0, "end": 4.5},
            {"text": "The pain is not severe, just annoying.", "start": 4.5, "end": 8.0},
        ],
    },
}


# ============================================================================
# FACT SAMPLES (for validation testing)
# ============================================================================

SAMPLE_FACTS = {
    "atomic_valid": {
        "fact_id": "fact_001",
        "transcription_id": "trans_001",
        "fact_text": "User's name is John Smith",
        "confidence_score": 0.95,
        "extraction_method": "cod",
        "source_span": {
            "start_char": 7,
            "end_char": 26,
            "text": "name is John Smith.",
        },
        "fact_version": "1.0",
        "timestamp": datetime.now().isoformat(),
    },

    "compound_invalid": {
        "fact_id": "fact_002",
        "transcription_id": "trans_002",
        "fact_text": "User has back pain and nausea and fever",  # Compound - invalid
        "confidence_score": 0.70,
        "extraction_method": "cod",
        "source_span": {
            "start_char": 7,
            "end_char": 29,
            "text": "back pain and nausea",
        },
        "fact_version": "1.0",
        "timestamp": datetime.now().isoformat(),
    },

    "vague_invalid": {
        "fact_id": "fact_003",
        "transcription_id": "trans_001",
        "fact_text": "User mentioned something about pain",  # Too vague
        "confidence_score": 0.50,
        "extraction_method": "cod",
        "source_span": {
            "start_char": 0,
            "end_char": 0,
            "text": "",
        },
        "fact_version": "1.0",
        "timestamp": datetime.now().isoformat(),
    },

    "hallucinated_entity": {
        "fact_id": "fact_004",
        "transcription_id": "trans_001",
        "fact_text": "User consulted Dr. Johnson",  # "Johnson" not in source
        "confidence_score": 0.80,
        "extraction_method": "cod",
        "source_span": {
            "start_char": -1,  # Invalid span (not found)
            "end_char": -1,
            "text": "",
        },
        "fact_version": "1.0",
        "timestamp": datetime.now().isoformat(),
    },

    "temporal_fact": {
        "fact_id": "fact_005",
        "transcription_id": "trans_001",
        "fact_text": "Headache started on Monday morning",
        "confidence_score": 0.92,
        "extraction_method": "cod",
        "source_span": {
            "start_char": 82,
            "end_char": 110,
            "text": "started on Monday morning",
        },
        "fact_version": "1.0",
        "timestamp": datetime.now().isoformat(),
    },
}


# ============================================================================
# COVE VERIFICATION SCENARIOS
# ============================================================================

COVE_SCENARIOS = {
    "pass_scenario": {
        "facts": [
            {
                "fact_text": "User's name is John Smith",
                "source_span": {"start_char": 12, "end_char": 32, "text": "my name is John Smith"},
            }
        ],
        "transcription": SAMPLE_TRANSCRIPTIONS["simple_medical"]["text"],
        "expected_decision": "PASS",
        "expected_violations": [],
        "expected_confidence": 0.95,
    },

    "needs_revision_scenario": {
        "facts": [
            {
                "fact_text": "User has back pain",
                "source_span": {"start_char": 7, "end_char": 21, "text": "back pain"},
            },
            {
                "fact_text": "User has fever",  # Not in source - MEDIUM violation
                "source_span": {"start_char": -1, "end_char": -1, "text": ""},
            },
            {
                "fact_text": "User has nausea",
                "source_span": {"start_char": 26, "end_char": 32, "text": "nausea"},
            },
        ],
        "transcription": SAMPLE_TRANSCRIPTIONS["compound_claims"]["text"],
        "expected_decision": "NEEDS_REVISION",
        "expected_violations": [
            {"severity": "MEDIUM", "fact": "User has fever"}
        ],
        "expected_confidence": 0.65,
    },

    "reject_scenario": {
        "facts": [
            {
                "fact_text": "User consulted Dr. Johnson yesterday",  # HIGH: invented entity
                "source_span": {"start_char": -1, "end_char": -1, "text": ""},
            }
        ],
        "transcription": SAMPLE_TRANSCRIPTIONS["simple_medical"]["text"],
        "expected_decision": "REJECT",
        "expected_violations": [
            {"severity": "HIGH", "fact": "User consulted Dr. Johnson yesterday"}
        ],
        "expected_confidence": 0.30,
    },
}


# ============================================================================
# GOLDEN TEST CASE TEMPLATES
# ============================================================================

def create_medical_case(
    condition: str,
    severity: str,
    duration: str,
    case_id: str = None
) -> Dict:
    """
    Generate medical test case from template.

    Args:
        condition: Medical condition (e.g., "headache", "back pain")
        severity: Severity level ("mild", "moderate", "severe")
        duration: Duration (e.g., "2 days", "a week")
        case_id: Optional ID (auto-generated if None)

    Returns:
        Test case dict with transcription, expected_facts, invalid_facts
    """
    case_id = case_id or f"medical_{uuid.uuid4().hex[:6]}"

    transcription = f"I have {condition}. It's {severity}. I've had it for {duration}."

    return {
        "id": case_id,
        "category": "medical",
        "transcription": transcription,
        "expected_facts": [
            {
                "fact_text": f"User has {condition}",
                "source_span": {
                    "start_char": transcription.find(condition),
                    "end_char": transcription.find(condition) + len(condition),
                    "text": condition,
                },
                "confidence_min": 0.90,
            },
            {
                "fact_text": f"Severity is {severity}",
                "source_span": {
                    "start_char": transcription.find(severity),
                    "end_char": transcription.find(severity) + len(severity),
                    "text": severity,
                },
                "confidence_min": 0.85,
            },
            {
                "fact_text": f"Duration is {duration}",
                "source_span": {
                    "start_char": transcription.find(duration),
                    "end_char": transcription.find(duration) + len(duration),
                    "text": duration,
                },
                "confidence_min": 0.85,
            },
        ],
        "invalid_facts": [
            f"User was prescribed medication",  # Not stated
            f"{condition.title()} caused by stress",  # Causal claim without evidence
        ],
        "metrics": {
            "expected_hallucination_rate": 0.0,
            "min_citation_coverage": 1.0,
        },
    }


def create_financial_case(
    amount: str,
    transaction: str,
    date: str,
    case_id: str = None
) -> Dict:
    """Generate financial test case from template."""
    case_id = case_id or f"financial_{uuid.uuid4().hex[:6]}"

    transcription = f"I {transaction} ${amount} on {date}."

    return {
        "id": case_id,
        "category": "financial",
        "transcription": transcription,
        "expected_facts": [
            {
                "fact_text": f"Transaction type: {transaction}",
                "confidence_min": 0.90,
            },
            {
                "fact_text": f"Amount: ${amount}",
                "confidence_min": 0.95,
            },
            {
                "fact_text": f"Date: {date}",
                "confidence_min": 0.90,
            },
        ],
        "invalid_facts": [
            f"Transaction was approved",  # Not stated
            f"Balance after: $X",  # Hallucinated calculation
        ],
        "metrics": {
            "expected_hallucination_rate": 0.0,
            "min_citation_coverage": 1.0,
        },
    }


# ============================================================================
# PYTEST FIXTURES (auto-imported when using conftest.py)
# ============================================================================

def get_sample_transcription(key: str) -> Dict:
    """Get sample transcription by key."""
    return SAMPLE_TRANSCRIPTIONS.get(key, SAMPLE_TRANSCRIPTIONS["simple_medical"])


def get_sample_fact(key: str) -> Dict:
    """Get sample fact by key."""
    return SAMPLE_FACTS.get(key, SAMPLE_FACTS["atomic_valid"])


def get_cove_scenario(key: str) -> Dict:
    """Get CoVe test scenario by key."""
    return COVE_SCENARIOS.get(key, COVE_SCENARIOS["pass_scenario"])


# ============================================================================
# BULK GENERATION HELPERS
# ============================================================================

def generate_medical_test_suite() -> List[Dict]:
    """Generate 12 medical test cases from template."""
    cases = []

    conditions = ["headache", "back pain", "nausea"]
    severities = ["mild", "severe"]
    durations = ["2 days", "a week"]

    for condition in conditions:
        for severity in severities:
            for duration in durations:
                cases.append(create_medical_case(condition, severity, duration))

    return cases


def generate_financial_test_suite() -> List[Dict]:
    """Generate 8 financial test cases from template."""
    cases = []

    transactions = ["spent", "received"]
    amounts = ["50", "200"]
    dates = ["Monday", "last week"]

    for transaction in transactions:
        for amount in amounts:
            for date in dates:
                cases.append(create_financial_case(amount, transaction, date))

    return cases


# ============================================================================
# EXPORTS
# ============================================================================

__all__ = [
    # Data
    "SAMPLE_TRANSCRIPTIONS",
    "SAMPLE_FACTS",
    "COVE_SCENARIOS",

    # Getters
    "get_sample_transcription",
    "get_sample_fact",
    "get_cove_scenario",

    # Generators
    "create_medical_case",
    "create_financial_case",
    "generate_medical_test_suite",
    "generate_financial_test_suite",
]
