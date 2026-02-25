# Risks

1. WebSocket tests depend on mocked transcribe path and may fail if patch target drifts.
2. Privacy strict mode can block transcriptions unexpectedly in noisy/PII-rich speech.
3. SQLite-first behavior differs from Supabase until migration 0008 is applied.
4. Existing dirty worktree may hide unrelated failures.
