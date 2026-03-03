-- 0015: Индексы для evidence_metadata и ui_hint запросов (v0.4.0 Visual Memory)
-- ПОЧЕМУ эти три индекса:
--   idx_se_acoustic_arousal  — фильтрация по эмоциональному возбуждению при построении EvidenceTrace
--   idx_se_sentiment_created — сортировка evidence по sentiment + времени (основной паттерн запроса)
--   idx_pi_person_created    — быстрый поиск взаимодействий персоны по времени для /graph/neighborhood

CREATE INDEX IF NOT EXISTS idx_se_acoustic_arousal
    ON structured_events(acoustic_arousal);

CREATE INDEX IF NOT EXISTS idx_se_sentiment_created
    ON structured_events(sentiment, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_pi_person_created
    ON person_interactions(person_name, created_at DESC);
