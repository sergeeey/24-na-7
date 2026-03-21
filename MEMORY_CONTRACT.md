# Memory Contract v1.0

## Canonical Data Flow

```
raw_audio → transcription → episode → structured_event → day_thread → long_thread
                                          ↓
                                    profile_facts
```

## Ownership Model

Every structured_event has:
- `owner_scope`: `self | other_person | mixed | unknown`
- `source_kind`: `user_speech | conversation | background_media | noise | system`
- `lineage_id`: links to source transcription for provenance

## Quality States

```
trusted → the event is verified user speech, quality checks passed
uncertain → ambiguous quality, may be noise or short
garbage → confirmed noise, TV subtitles, repeated phrases
quarantined → contradictory data, needs manual review
```

## Truth Evaluation Signals (priority order)

1. **Ownership** (primary): is_user from speaker verification
   - NON_USER_SPEAKER: is_user=False → -0.4
   - ALL_BACKGROUND: episode with 0 user transcriptions → -0.5
   - MIXED_OWNERSHIP: <50% user in episode → -0.15
   - LOW_SPEAKER_CONFIDENCE: confidence < 0.3 → -0.1

2. **Content** (secondary): token analysis
   - EMPTY_TRANSCRIPT: 0 tokens → -1.0
   - LOW_INFORMATION: <2 tokens or unique_ratio <0.3 → -0.25
   - REPEATED_PHRASE: dominant word >=45% → -0.45
   - DUPLICATE_NEIGHBOR: same text nearby → -0.3

3. **Threshold**: score < 0.72 → uncertain

## Required Fields Per Level

### transcription
- id, text, created_at, is_user, speaker_confidence, quality_state

### episode
- id, started_at, ended_at, quality_state, source_count, day_key

### structured_event
- id, transcription_id, text, created_at, is_current
- owner_scope, source_kind, lineage_id
- quality_state (from truth evaluation, NOT migration default)
- emotions, topics, domains, speakers, sentiment

### day_thread / long_thread
- id, day_key, topic, quality from constituent episodes

## Backfill Contract

When adding new quality fields:
1. Add with DEFAULT NULL (not optimistic defaults)
2. Classify from source data (transcriptions.is_user → owner_scope)
3. Re-evaluate truth honestly
4. Verify distribution matches expectations
