# Reflexio 24/7

**Evidence-based digital mirror — passive memory that reflects who you are**
*Цифровое зеркало на основе доказательной памяти*

![Python 3.11+](https://img.shields.io/badge/Python-3.11+-blue?logo=python)
![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-009688?logo=fastapi)
![Kotlin](https://img.shields.io/badge/Kotlin-Android-7F52FF?logo=kotlin)
![Docker](https://img.shields.io/badge/Docker-ready-2496ED?logo=docker)
![Version](https://img.shields.io/badge/version-0.5.2--beta-orange)
![Tests](https://img.shields.io/badge/tests-697%20passed-brightgreen)
![License: MIT](https://img.shields.io/badge/License-MIT-green)

---

## What is Reflexio?

Reflexio is a **digital mirror** — not a voice diary, not a smart recorder.

Your phone captures speech 24/7. The system transcribes it, determines whose voice it is, enriches with context (emotions, topics, people, commitments), stores permanently as structured memory, and reflects it back through 5 canonical questions:

1. **Who am I becoming?** — emotional baseline, recurring topics, active hours
2. **What influences me?** — people, places, content consumption
3. **What patterns repeat?** — unresolved commitments, behavioral loops
4. **What's changing?** — drift signals vs 7/30 day baseline
5. **Why does the system think so?** — evidence trail with confidence and lineage

**Key question:** *"What did I talk about with Marat in January?"*
**System answer:** finds, summarizes, shows patterns — with evidence.

**North Star:** *The user reads their evening digest and discovers something important about themselves they hadn't noticed.*

### What Reflexio is NOT

- Not a transcription service (transcription is just the substrate)
- Not a daily diary (accumulation over months/years is the point)
- Not an analytics dashboard (mirror reflects, doesn't just chart)
- Not an AI advisor — yet (guidance is north star, not current scope)

---

## Architecture

```
Capture              Memory Backbone              Mirror
─────────            ───────────────              ──────
Phone 24/7           Transcription                Identity
  → VAD                → Episode                  Influences
  → Speaker ID           → Structured Event       Patterns
  → Upload                 → Day Thread           Drift
                             → Long Thread        Evidence
                               → Profile

Truth Layer: trusted / uncertain / garbage / quarantined
Ownership:   self / other_person / mixed / unknown
```

### Canonical Data Flow

```
raw_audio → transcription → episode → structured_event → day_thread → long_thread
                                          ↓
                                    mirror payload
```

Every level has: `quality_state`, `owner_scope`, `evidence_strength`, `lineage_id`.
See [MEMORY_CONTRACT.md](MEMORY_CONTRACT.md) for the full data contract.

---

## Product Loop

```
RECORD → MEMORY → ASK → MIRROR
  ↑                        |
  └────── feedback ────────┘
```

| Tab | Purpose |
|-----|---------|
| **RECORD** | Always-on capture with speaker verification |
| **DAY** | Daily digest with calendar, emotions, evidence |
| **ASK** | Natural language queries to your memory (`POST /ask`) |
| **PEOPLE** | Social graph — who matters, interaction history |
| **MIRROR** | Digital portrait — identity, influences, patterns, drift |

---

## Features

### Core Pipeline
- **24/7 Capture** — Android foreground service, VAD segmentation, offline queue
- **Speaker Verification** — resemblyzer GE2E embeddings, user vs background separation
- **ASR** — faster-whisper (medium, int8, local inference)
- **LLM Enrichment** — Gemini Flash → Claude Haiku → GPT-4o-mini cascade
- **Ownership-Aware Truth Layer** — quality evaluation based on who spoke, not just word count

### Memory Backbone
- **Episodic Memory** — `episode → day_thread → long_thread` hierarchy
- **Quality States** — `trusted / uncertain / garbage / quarantined`
- **Ownership** — `self / other_person / mixed / unknown` per event
- **Evidence Lineage** — every fact traces back to source transcription
- **Cascade Integrity** — source truth auto-propagates to derived layer

### Intelligence
- **One Interface** — `POST /ask` with evidence-based answers and confidence
- **Mirror Portrait** — 5-section canonical payload (identity, influences, patterns, drift, evidence)
- **Memory Observability** — `/mirror/memory-quality` for operational health
- **Balance Wheel** — 8 life domains tracked from speech
- **Social Graph** — automatic people tracking with KuzuDB

### Security & Privacy
- **Zero-retention** — audio deleted after transcription
- **SQLCipher AES-256** — database encryption at rest
- **PII masking** — before LLM enrichment
- **GDPR erase** — delete all data for a person
- **Bearer auth** — on all endpoints

---

## Quick Start

### Docker (recommended)

```bash
git clone https://github.com/sergeeey/24-na-7.git
cd 24-na-7
cp .env.example .env   # fill in API keys
docker compose up -d
curl http://localhost:8000/health
# → {"status":"ok","version":"0.5.2-beta"}
```

### Local development

```bash
python -m venv venv && source venv/bin/activate
pip install -e ".[dev]"
uvicorn src.api.main:app --reload --host 0.0.0.0 --port 8000
pytest tests/  # 697 passed
```

Android app: open `android/` in Android Studio, build debug APK.

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Mobile | Kotlin, Jetpack Compose, Room, WorkManager |
| Backend | Python 3.11+, FastAPI, Pydantic, structlog |
| ASR | faster-whisper (local, medium int8) |
| LLM | Gemini Flash / Claude Haiku / GPT-4o-mini (cascade) |
| Speaker ID | resemblyzer (GE2E, 256-dim d-vectors) |
| Database | SQLite + SQLCipher (AES-256) |
| Graph | KuzuDB (temporal social graph) |
| Queue | Redis + APScheduler |
| Deploy | Docker Compose, Caddy (TLS), systemd |

---

## Key API Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/ask` | One Interface — ask anything about your memory |
| `GET` | `/mirror/portrait` | Digital mirror — 5-section canonical payload |
| `GET` | `/mirror/memory-quality` | Memory observability — ownership, quality, invariants |
| `POST` | `/ingest/audio` | Upload audio segment |
| `GET` | `/digest/today` | Today's digest |
| `GET` | `/query/events` | Search structured events |
| `GET` | `/query/threads` | Long-term continuity lines |
| `GET` | `/graph/persons` | Social graph |
| `GET` | `/ingest/pipeline-status` | Pipeline health + SLO state |
| `POST` | `/admin/reclassify` | Re-evaluate truth layer (dry_run/apply) |

---

## Current State

**Version:** `v0.5.2-beta` (deployed, dogfooding active)

| Metric | Value |
|--------|-------|
| Structured events | 5,154+ |
| Episodes | 2,451+ |
| Long threads | 317+ |
| Tests | 697 passed, 0 failed |
| Trusted fraction | 15.8% (honest, post-backfill) |
| Ownership classified | 100% (self: 1047, other: 1302) |
| Invariants | OK (0 NULLs in quality/ownership) |
| Lineage coverage | 100% |

### Maturity Levels

| Level | Name | Status |
|-------|------|--------|
| **L1** | Fixation (capture → store → digest) | ~90% |
| **L2** | Understanding (patterns, emotions, people) | ~40% |
| **L3** | Cognitive Twin (prediction, guidance) | Concept |

---

## Documentation

| Doc | Description |
|-----|-------------|
| [MEMORY_CONTRACT.md](MEMORY_CONTRACT.md) | Canonical data contract — fields, quality states, ownership |
| [PROJECT.md](PROJECT.md) | Full technical specification |
| [CLAUDE.md](CLAUDE.md) | AI assistant configuration |

---

## License

MIT

## Author

Sergey Boyko — Almaty, KZ
