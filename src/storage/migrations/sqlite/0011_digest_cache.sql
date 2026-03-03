-- 0011: Таблица кеша pre-computed дайджестов
-- ПОЧЕМУ: endpoint /digest/daily делает 3-5 LLM вызовов (4+ мин).
-- Pre-compute через APScheduler → кеш → мгновенный ответ клиенту.

CREATE TABLE IF NOT EXISTS digest_cache (
    date       TEXT    PRIMARY KEY,
    digest_json TEXT   NOT NULL,
    generated_at TEXT  NOT NULL,
    status     TEXT    NOT NULL DEFAULT 'ready'
    -- status: 'generating' | 'ready' | 'failed'
);
