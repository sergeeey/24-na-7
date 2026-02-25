# Semantic Memory + Integrity Implementation Spec

## Objective
Unify ingest/websocket/asr into one security-consistent processing model:
- Local-first privacy modes (strict/mask/audit)
- Cryptographic integrity chain for ingest artifacts
- Semantic memory retrieval with evidence

## Runtime paths
- /ingest/audio
- /ws/ingest
- /asr/transcribe

## New API
- GET /memory/retrieve
- GET /audit/ingest/{ingest_id}
