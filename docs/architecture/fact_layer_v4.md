# Fact Layer Architecture — Reflexio 24/7 v4

**Version:** 4.0
**Date:** 2026-02-17
**Status:** 🚧 In Development

---

## Overview

The Fact Layer is the core anti-hallucination system for Reflexio 24/7 v4. It ensures every claim in a digest is grounded in source transcriptions with verifiable citations.

**Key Principles:**
1. **LLM is NOT a source of facts** - only extracts facts from transcriptions
2. **Every fact has a source span** - character offsets in transcription
3. **Immutable fact storage** - append-only, no UPDATE allowed
4. **Chain-of-Verification (CoVe)** - hallucination detection before digest generation

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                        REFLEXIO v4 FACT PIPELINE                     │
└─────────────────────────────────────────────────────────────────────┘

    ┌────────────┐
    │ Audio File │
    └─────┬──────┘
          │
          ▼
    ┌─────────────────┐
    │  ASR (Whisper)  │──────┐
    │  faster-whisper │      │ metadata
    └────────┬────────┘      │ (confidence,
             │               │  language)
             │               ▼
             │        ┌──────────────┐
             ▼        │ transcriptions│
    ┌────────────────┐│     table     │
    │ Transcription  │└──────────────┘
    │   with         │
    │   segments     │
    └────────┬───────┘
             │
             ▼
    ┌──────────────────────────────┐
    │ DIGEST GENERATOR (existing)  │
    │  - Chain of Density (CoD)    │
    │  - DeepConf confidence       │
    └────────┬─────────────────────┘
             │ summary
             │
             ▼
    ┌──────────────────────────────┐
    │  ✨ FACT EXTRACTOR (NEW v4) │
    │  Stage 1: LLM extraction     │
    │  Stage 2: Source grounding   │
    └────────┬─────────────────────┘
             │ candidate facts
             │
             ▼
    ┌──────────────────────────────┐
    │  ✨ VALIDATORS (NEW v4)      │
    │  - Atomicity (single claim)  │
    │  - Grounding (in source?)    │
    │  - Consistency (no conflict) │
    │  - Specificity (not vague)   │
    └────────┬─────────────────────┘
             │ validated facts
             │
             ▼
    ┌──────────────────────────────┐
    │  ✨ CoVe PIPELINE (NEW v4)   │◀─── Optional (config flag)
    │  1. Plan (generate questions)│
    │  2. Execute (answer from src)│
    │  3. Verify (consistency)     │
    │  4. Final (adjust confidence)│
    └────────┬─────────────────────┘
             │ verified facts
             │
             ▼
    ┌──────────────────────────────┐
    │  ✨ FACT STORE (NEW v4)      │
    │   facts table                │
    │   - fact_id (PK)             │
    │   - transcription_id (FK)    │
    │   - fact_text                │
    │   - source_span (JSON)       │
    │   - confidence_score         │
    │   - fact_version ("1.0")     │
    └──────────────────────────────┘
```

---

## Component Details

### 1. Fact Extractor (`src/digest/fact_extractor.py`)

**Purpose:** Extract atomic facts from Chain-of-Density summary and map to source text.

**Algorithm:**
```python
def extract_facts(summary: str, transcription: Transcription) -> List[Fact]:
    # Stage 1: LLM Extraction
    prompt = f"""
    Extract atomic facts from this summary.
    Rules:
    - One claim per fact (no "and")
    - Specific (no "something", "things")
    - Verifiable (not opinion)

    Summary: {summary}
    """
    response = llm.generate(prompt)
    candidate_facts = parse_llm_response(response)

    # Stage 2: Source Grounding (fuzzy matching)
    grounded_facts = []
    for candidate in candidate_facts:
        span = find_source_span(
            candidate.text,
            transcription.text,
            threshold=0.8  # 80% fuzzy match
        )
        if span:
            grounded_facts.append(Fact(
                fact_text=candidate.text,
                source_span=span,
                confidence_score=calculate_confidence(span),
                extraction_method="cod"
            ))

    return grounded_facts
```

**Key Dependencies:**
- `rapidfuzz` library for fuzzy matching
- Existing `LLMProvider` (`src/llm/providers.py`)
- Pydantic models (`src/models/fact.py`)

---

### 2. Validators (`src/digest/validators.py`)

**Purpose:** Multi-layer validation to catch invalid facts before storage.

**Validators:**

```python
class FactValidator:
    async def validate_fact(self, fact: Fact, context: Context) -> ValidationResult:
        results = await asyncio.gather(
            self._validate_atomicity(fact),      # No compound claims
            self._validate_grounding(fact, ctx), # Fact in source?
            self._validate_consistency(fact),    # No contradictions?
            self._validate_specificity(fact)     # Not vague?
        )
        return ValidationResult.aggregate(results)
```

**Validation Rules:**

| Validator | Rule | Example PASS | Example FAIL |
|-----------|------|--------------|--------------|
| **Atomicity** | Single claim only | "User has headache" | "User has headache and nausea" |
| **Grounding** | Text appears in source | "Name is John Smith" (source: "my name is John Smith") | "Name is Dr. Johnson" (not in source) |
| **Consistency** | No contradictions | "No fever" (source: "I don't have fever") | "Has fever" (source: "no fever") |
| **Specificity** | Concrete claims | "Headache started Monday" | "User mentioned something" |

---

### 3. CoVe Pipeline (`src/digest/cove_pipeline.py`)

**Purpose:** Chain-of-Verification to detect and filter hallucinations.

**4-Stage Process:**

```python
class CoVePipeline:
    async def verify_facts(
        self,
        facts: List[Fact],
        context: TranscriptionContext
    ) -> List[VerifiedFact]:

        # Stage 1: Planning
        questions = await self._generate_verification_questions(facts)
        # Example: Fact "User has headache" → Q: "Does the user have a headache?"

        # Stage 2: Execution
        answers = await self._answer_from_source(questions, context.transcription)
        # Answer ONLY from source, no external knowledge

        # Stage 3: Verification
        results = await self._verify_consistency(facts, answers)
        # Compare fact claim with answer:
        #   - Consistent → confidence ×1.2
        #   - Inconsistent → confidence ×0.5
        #   - Not stated → confidence ×0.7

        # Stage 4: Final
        verified_facts = self._adjust_confidence(facts, results)
        # Filter out low-confidence facts (<threshold)

        return verified_facts
```

**CoVe Decision Logic:**
```python
def decide_cove(violations: List[Dict]) -> str:
    high = sum(1 for v in violations if v['severity'] == 'HIGH')
    medium = sum(1 for v in violations if v['severity'] == 'MEDIUM')

    if high >= 1:
        return "REJECT"  # At least 1 HIGH violation
    elif medium >= 3:
        return "NEEDS_REVISION"  # Too many MEDIUM
    else:
        return "PASS"  # Mostly LOW or none
```

---

### 4. Fact Store (`src/storage/fact_store.py`)

**Purpose:** Persist facts with immutability guarantees.

**Database Schema:**
```sql
-- Existing table (from 0001_init.sql)
CREATE TABLE facts (
    id TEXT PRIMARY KEY,
    transcription_id TEXT,
    fact_text TEXT NOT NULL,
    timestamp TIMESTAMP NOT NULL,
    confidence REAL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- NEW columns (from 0002_fact_v4_columns.sql)
ALTER TABLE facts ADD COLUMN extracted_by TEXT DEFAULT 'v4-cove';
ALTER TABLE facts ADD COLUMN fact_version TEXT DEFAULT '1.0';
ALTER TABLE facts ADD COLUMN confidence_score REAL;
ALTER TABLE facts ADD COLUMN extraction_method TEXT;  -- 'cod' | 'deepconf' | 'cove'
ALTER TABLE facts ADD COLUMN source_span TEXT;  -- JSON: {start_char, end_char, text}

-- Indexes for performance
CREATE INDEX idx_facts_version ON facts(fact_version);
CREATE INDEX idx_facts_transcription ON facts(transcription_id);
CREATE INDEX idx_facts_confidence ON facts(confidence_score);
```

**Immutability Enforcement:**
```python
class FactStore:
    async def store_facts(self, facts: List[Fact]):
        """Append-only insert. No UPDATE/DELETE allowed."""
        async with self.db.transaction():
            for fact in facts:
                # INSERT only
                await self.db.execute(
                    "INSERT INTO facts (...) VALUES (...)",
                    (fact.fact_id, fact.transcription_id, ...)
                )
                # Audit log
                await self.audit_log.log("CREATE", fact.fact_id)

    # No update_fact() method - intentionally removed
    # No delete_fact() method - use soft delete via retention policy
```

---

## Data Models

### Fact (Pydantic)

```python
class SourceSpan(BaseModel):
    """Exact text span from transcription."""
    start_char: int = Field(ge=0, description="Start character offset")
    end_char: int = Field(ge=0, description="End character offset")
    text: str = Field(description="Exact text from source")

    @validator("end_char")
    def validate_span(cls, v, values):
        if v <= values.get("start_char", 0):
            raise ValueError("end_char must be > start_char")
        return v

class Fact(BaseModel):
    """Atomic, verifiable claim from transcription."""
    fact_id: str = Field(default_factory=lambda: f"fact_{uuid4().hex[:12]}")
    transcription_id: str
    fact_text: str = Field(min_length=10, max_length=500)
    confidence_score: float = Field(ge=0.0, le=1.0)
    extraction_method: Literal["cod", "deepconf", "cove"]
    source_span: SourceSpan
    fact_version: str = "1.0"
    timestamp: datetime

    @validator("fact_text")
    def validate_atomicity(cls, v):
        """Ensure fact is atomic (no compound claims)."""
        if " and " in v.lower() or ";" in v:
            raise ValueError("Fact must be atomic (single claim)")
        return v
```

---

## Integration Points

### Existing Code Modifications

```python
# src/digest/generator.py (MODIFY - add ~120 lines)

class DigestGenerator:
    def __init__(self, ...):
        ...
        # NEW: v4 components
        self.fact_extractor = FactExtractor(self.llm_provider)
        self.fact_validator = FactValidator()
        self.cove_pipeline = CoVePipeline(self.llm_provider)
        self.fact_store = FactStore(self.db)

    async def generate(self, transcription_id: str, **kwargs):
        # ... existing CoD logic ...
        summary = await self._generate_summary(transcription)

        # ✨ NEW: Fact extraction (line ~580)
        facts = await self.fact_extractor.extract_facts(
            summary, transcription
        )

        # ✨ NEW: Validation
        validated_facts = []
        for fact in facts:
            result = await self.fact_validator.validate_fact(
                fact, TranscriptionContext(transcription)
            )
            if result.is_valid:
                validated_facts.append(fact)

        # ✨ NEW: Optional CoVe verification (line ~620)
        if self.config.enable_cove:
            validated_facts = await self.cove_pipeline.verify_facts(
                validated_facts, TranscriptionContext(transcription)
            )

        # ✨ NEW: Storage
        await self.fact_store.store_facts(validated_facts)

        # ... existing digest assembly ...
        return digest
```

### Configuration

```python
# src/utils/config.py (MODIFY - add ~20 lines)

class Settings(BaseSettings):
    ...
    # v4 Fact Layer
    ENABLE_COVE: bool = Field(default=False, env="ENABLE_COVE")
    COVE_CONFIDENCE_THRESHOLD: float = Field(default=0.7)
    COVE_MAX_VERIFICATION_ROUNDS: int = Field(default=2)

    # Fact extraction
    FACT_EXTRACTION_MIN_LENGTH: int = Field(default=10)
    FACT_EXTRACTION_MAX_LENGTH: int = Field(default=500)
    FACT_GROUNDING_THRESHOLD: float = Field(default=0.8)  # Fuzzy match
```

---

## Backward Compatibility

**API Changes:**
```python
# src/api/routers/digest.py (MODIFY - add optional params)

@router.get("/digest/{transcription_id}")
async def get_digest(
    transcription_id: str,
    include_facts: bool = Query(False),  # ✨ NEW (opt-in)
    fact_version: str = Query("1.0"),   # ✨ NEW
    db: Database = Depends(get_db)
):
    """Get digest with optional facts."""
    digest = await DigestGenerator(db).generate(transcription_id)

    # ✨ NEW: Facts are additive (backward compatible)
    if include_facts:
        facts = await FactStore(db).get_facts(
            transcription_id, version=fact_version
        )
        digest["facts"] = [f.dict() for f in facts]

    return digest
```

**No Breaking Changes:**
- Old API calls work unchanged (facts not included by default)
- Existing digests unaffected
- Database migration extends table (no data loss)

---

## Performance Considerations

### Latency Budget

| Component | Target p95 Latency | Notes |
|-----------|-------------------|-------|
| Fact Extraction | ≤800ms | LLM call + fuzzy matching |
| Validation | ≤100ms | Pydantic + regex |
| CoVe Pipeline | ≤500ms | 4 stages, optimized prompts |
| Storage | ≤50ms | Batch INSERT |
| **Total Overhead** | **≤1.5s** | Added to existing digest generation |

### Optimization Strategies

1. **Parallel Validation:** Run 4 validators concurrently with `asyncio.gather`
2. **CoVe Caching:** Cache verification results for repeated facts
3. **Batch Storage:** INSERT multiple facts in single transaction
4. **Optional CoVe:** Disable via config flag if latency critical

---

## Testing Strategy

### Test Coverage Targets

| Module | Target Coverage |
|--------|----------------|
| `src/models/fact.py` | 100% |
| `src/digest/validators.py` | ≥80% |
| `src/digest/fact_extractor.py` | ≥80% |
| `src/digest/cove_pipeline.py` | ≥80% |
| `src/storage/fact_store.py` | ≥75% |

### Test Types

```
tests/
├── test_fact_validation.py         # Unit: Pydantic models, validators
├── test_fact_extractor.py          # Unit: Extraction logic
├── test_cove_pipeline.py           # Unit: CoVe stages
├── integration/
│   └── test_fact_pipeline.py       # Integration: End-to-end flow
└── golden/
    ├── test_golden_set.py          # Regression: Anti-hallucination
    └── cases/
        ├── case_001_simple.yaml
        └── ... (20+ cases)
```

---

## Success Metrics

### Phase Targets

| Phase | Hallucination Rate | Citation Coverage | Test Coverage |
|-------|-------------------|------------------|---------------|
| Baseline (v3) | ~2-5% | 0% | 2.1% |
| M2 Complete | ≤3% | ≥90% | ≥80% |
| M3 Complete | ≤1% | ≥95% | ≥80% |
| **v4 Complete** | **≤0.5%** | **≥98%** | **≥80%** |

---

## Future Enhancements (v4.1+)

1. **Pattern Engine** (deferred from v4.0)
   - Entity resolution across transcriptions
   - Frequency-based pattern detection
   - LLM-powered entity linking

2. **Multi-lingual Support**
   - Language-specific fact extractors
   - Cross-lingual entity matching

3. **Fact Versioning**
   - Track fact evolution over time
   - Conflict resolution for contradictory facts

4. **Advanced CoVe**
   - Multi-round verification
   - External knowledge grounding (with citations)
   - Confidence calibration ML model

---

## References

- [TECH SPEC v4](../../TECH_SPEC_V4_2026.md)
- [Implementation Plan](../../../.claude/plans/nifty-beaming-coral.md)
- [Baseline Metrics](../BASELINE_METRICS.md)

---

**Last Updated:** 2026-02-17
**Status:** 🚧 M0 Complete, M1 In Progress
