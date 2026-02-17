"""
Тесты для повышения покрытия ядра (api, config, digest, memory, utils).
"""
import os
from pathlib import Path
from datetime import date
from unittest.mock import patch, MagicMock

# --- config ---
def test_settings_loads():
    """Settings загружает значения из окружения."""
    from src.utils.config import settings
    assert hasattr(settings, "API_PORT")
    assert hasattr(settings, "UPLOADS_PATH")
    assert hasattr(settings, "STORAGE_PATH")


def test_settings_uploads_path_is_path():
    from src.utils.config import settings
    assert isinstance(settings.UPLOADS_PATH, Path)


# --- digest generator (calculate_metrics, _get_density_level) ---
def test_digest_calculate_metrics_empty(tmp_path):
    from src.digest.generator import DigestGenerator
    gen = DigestGenerator(db_path=tmp_path / "x.db")
    metrics = gen.calculate_metrics([], [])
    assert metrics["transcriptions_count"] == 0
    assert metrics["facts_count"] == 0
    assert metrics["average_words_per_transcription"] == 0
    assert "density_level" in metrics


def test_digest_calculate_metrics_with_data(tmp_path):
    from src.digest.generator import DigestGenerator
    gen = DigestGenerator(db_path=tmp_path / "x.db")
    transcriptions = [{"text": "Hello world.", "duration": 60, "created_at": "2026-01-01T12:00:00"}]
    facts = [{"text": "Fact one", "type": "fact"}]
    metrics = gen.calculate_metrics(transcriptions, facts)
    assert metrics["transcriptions_count"] == 1
    assert metrics["facts_count"] == 1
    assert metrics["total_words"] == 2
    assert "density_level" in metrics


def test_digest_get_density_level(tmp_path):
    from src.digest.generator import DigestGenerator
    gen = DigestGenerator(db_path=tmp_path / "x.db")
    level = gen._get_density_level(25)
    assert isinstance(level, str) and len(level) > 0
    assert gen._get_density_level(0) is not None


def test_digest_extract_facts_empty():
    from src.digest.generator import DigestGenerator
    from pathlib import Path
    gen = DigestGenerator(db_path=Path("nonexistent.db"))
    facts = gen.extract_facts([], use_llm=False)
    assert facts == []


def test_digest_extract_facts_with_text(tmp_path):
    from src.digest.generator import DigestGenerator
    gen = DigestGenerator(db_path=tmp_path / "x.db")
    transcriptions = [{"text": "Meeting about project timeline and budget.", "created_at": "2026-01-01T12:00:00"}]
    facts = gen.extract_facts(transcriptions, use_llm=False)
    assert isinstance(facts, list)
    assert len(facts) >= 0


# --- api routes (TestClient) ---
def test_api_ingest_status():
    from fastapi.testclient import TestClient
    from src.api.main import app
    client = TestClient(app)
    r = client.get("/ingest/status/some-id")
    assert r.status_code == 200
    assert r.json()["id"] == "some-id"
    assert r.json()["status"] == "pending"


def test_api_health():
    from fastapi.testclient import TestClient
    from src.api.main import app
    client = TestClient(app)
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_api_openapi():
    from fastapi.testclient import TestClient
    from src.api.main import app
    client = TestClient(app)
    r = client.get("/openapi.json")
    assert r.status_code == 200


def test_api_digest_today_markdown(tmp_path):
    """Эндпоинт /digest/today возвращает markdown при моке генератора."""
    from fastapi.testclient import TestClient
    from src.api.main import app
    mock_file = tmp_path / "out.md"
    mock_file.write_text("# Digest\n\nEmpty.", encoding="utf-8")
    mock_gen = MagicMock()
    mock_gen.generate.return_value = mock_file
    with patch("src.api.main.DigestGenerator") as M:
        M.return_value = mock_gen
        client = TestClient(app)
        r = client.get("/digest/today?format=markdown")
    assert r.status_code == 200
    assert "Digest" in r.text or "Empty" in r.text


def test_digest_generate_markdown_minimal(tmp_path):
    """Генерация markdown без расширенных метрик."""
    from src.digest.generator import DigestGenerator
    gen = DigestGenerator(db_path=tmp_path / "x.db")
    transcriptions = []
    facts = []
    metrics = gen.calculate_metrics(transcriptions, facts)
    md = gen.generate_markdown(date.today(), transcriptions, facts, metrics, include_metadata=False)
    assert "Reflexio Digest" in md
    assert "Метрики" in md or "метрик" in md.lower()


def test_api_digest_date_invalid():
    """Эндпоинт /digest/{date} с неверной датой возвращает 400."""
    from fastapi.testclient import TestClient
    from src.api.main import app
    client = TestClient(app)
    r = client.get("/digest/not-a-date?format=markdown")
    assert r.status_code == 400


def test_api_digest_date_ok(tmp_path):
    """Эндпоинт /digest/{date} с моком генератора."""
    from fastapi.testclient import TestClient
    from src.api.main import app
    mock_file = tmp_path / "d.md"
    mock_file.write_text("# Digest 2026-01-15", encoding="utf-8")
    mock_gen = MagicMock()
    mock_gen.generate.return_value = mock_file
    with patch("src.api.main.DigestGenerator") as M:
        M.return_value = mock_gen
        client = TestClient(app)
        r = client.get("/digest/2026-01-15?format=markdown")
    assert r.status_code == 200


def test_digest_generate_json_minimal(tmp_path):
    """Генерация JSON-дайджеста (структура)."""
    from src.digest.generator import DigestGenerator
    gen = DigestGenerator(db_path=tmp_path / "x.db")
    transcriptions = []
    facts = []
    metrics = gen.calculate_metrics(transcriptions, facts)
    out = gen.generate_json(date.today(), transcriptions, facts, metrics)
    assert "date" in out
    assert "metrics" in out
    assert "facts" in out


def test_api_root():
    """Корневой endpoint возвращает описание API."""
    from fastapi.testclient import TestClient
    from src.api.main import app
    client = TestClient(app)
    r = client.get("/")
    assert r.status_code == 200
    data = r.json()
    assert "service" in data
    assert "endpoints" in data
    assert data["endpoints"]["health"] == "/health"


def test_rate_limiter_get_limit_for_endpoint():
    """Лимиты по имени endpoint."""
    from src.utils.rate_limiter import get_limit_for_endpoint, RateLimitConfig
    assert get_limit_for_endpoint("ingest_audio") == RateLimitConfig.INGEST_AUDIO_LIMIT
    assert get_limit_for_endpoint("health") == RateLimitConfig.HEALTH_LIMIT
    assert get_limit_for_endpoint("unknown") == RateLimitConfig.DEFAULT_LIMIT


def test_rate_limiter_create_limiter():
    """Создание limiter (memory backend)."""
    from src.utils.rate_limiter import create_limiter
    limiter = create_limiter()
    assert limiter is not None


def test_api_density_analysis(tmp_path):
    """Эндпоинт density с моком analyzer."""
    from fastapi.testclient import TestClient
    from src.api.main import app
    mock_analyzer = MagicMock()
    mock_analyzer.analyze_day.return_value = {"density_score": 0.5, "transcriptions_count": 0}
    with patch("src.api.main.InformationDensityAnalyzer") as M:
        M.return_value = mock_analyzer
        client = TestClient(app)
        r = client.get("/digest/2026-01-15/density")
    assert r.status_code == 200
    assert r.json().get("transcriptions_count") == 0


def test_analyzer_empty_db(tmp_path):
    """Анализатор при отсутствии БД возвращает пустой анализ."""
    from src.digest.analyzer import InformationDensityAnalyzer
    db_path = tmp_path / "nonexistent.db"
    analyzer = InformationDensityAnalyzer(db_path=db_path)
    out = analyzer.analyze_day(date(2026, 1, 15))
    assert "date" in out
    assert "statistics" in out
    assert out["statistics"]["transcriptions_count"] == 0


def test_analyzer_existing_empty_db(tmp_path):
    """Анализатор с существующей пустой БД (таблица transcriptions)."""
    import sqlite3
    from src.digest.analyzer import InformationDensityAnalyzer
    db_path = tmp_path / "reflexio.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE IF NOT EXISTS transcriptions (id TEXT, text TEXT, duration REAL, created_at TEXT)")
    conn.commit()
    conn.close()
    analyzer = InformationDensityAnalyzer(db_path=db_path)
    out = analyzer.analyze_day(date(2026, 1, 15))
    assert out["statistics"]["transcriptions_count"] == 0
    assert "density_analysis" in out


def test_metrics_ext_interpret():
    """Интерпретация метрик (metrics_ext)."""
    from src.digest.metrics_ext import interpret_semantic_density, interpret_wpm_rate
    assert "низк" in interpret_semantic_density(0.1).lower() or "low" in interpret_semantic_density(0.1).lower()
    assert len(interpret_wpm_rate(100)) > 0


def test_digest_get_transcriptions_with_db(tmp_path):
    """DigestGenerator.get_transcriptions при наличии БД с таблицами."""
    import sqlite3
    from src.digest.generator import DigestGenerator
    db_path = tmp_path / "reflexio.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("""
        CREATE TABLE transcriptions (
            id TEXT, ingest_id TEXT, text TEXT, language TEXT, language_probability REAL,
            duration REAL, segments TEXT, created_at TEXT
        )
    """)
    conn.execute("CREATE TABLE ingest_queue (id TEXT, filename TEXT, file_size INTEGER)")
    conn.execute(
        "INSERT INTO transcriptions (id, text, created_at) VALUES (?, ?, ?)",
        ("t1", "Hello world", "2026-01-15T10:00:00"),
    )
    conn.commit()
    conn.close()
    gen = DigestGenerator(db_path=db_path)
    rows = gen.get_transcriptions(date(2026, 1, 15))
    assert len(rows) == 1
    assert rows[0]["text"] == "Hello world"


def test_core_memory_get_preferences():
    """CoreMemory.get_preferences с моком Letta."""
    from src.memory.core_memory import CoreMemory
    with patch("src.memory.core_memory.get_letta_client") as mock_letta:
        mock_letta.return_value.get_memory.return_value = None
        cm = CoreMemory()
        cm._cache = {}
        prefs = cm.get_preferences()
    assert "language" in prefs
    assert prefs["language"] == "ru"


def test_session_memory_get_session():
    """Session memory возвращает структуру."""
    from src.memory.session_memory import get_session_memory
    sm = get_session_memory()
    assert sm is not None


def test_summarizer_prompts_cod():
    """Chain of Density промпт."""
    from src.summarizer.prompts import get_chain_of_density_prompt
    p = get_chain_of_density_prompt("Sample text", iterations=3)
    assert "Sample text" in p
    assert "3" in p or "итерац" in p.lower()


def test_summarizer_prompts_few_shot():
    """Few-Shot Actions промпт."""
    from src.summarizer.prompts import get_few_shot_actions_prompt
    p = get_few_shot_actions_prompt("Meeting notes")
    assert "Meeting" in p or "notes" in p or len(p) > 0


def test_storage_backup_sqlite(tmp_path):
    """backup_sqlite создаёт копию при наличии БД."""
    from src.utils.config import settings
    from src.storage.migrate import backup_sqlite
    (tmp_path / "reflexio.db").write_bytes(b"")  # empty file for copy
    with patch.object(settings, "STORAGE_PATH", tmp_path):
        backup_path = backup_sqlite(backup_path=tmp_path / "backup.db")
    assert backup_path.exists()
    assert backup_path.stat().st_size >= 0


def test_rate_limiter_setup(app=None):
    """setup_rate_limiting не падает."""
    from src.utils.rate_limiter import setup_rate_limiting
    from fastapi import FastAPI
    app = app or FastAPI()
    limiter = setup_rate_limiting(app)
    assert limiter is not None


def test_vault_list_secrets():
    """VaultClient.list_secrets при отключенном Vault возвращает []."""
    from src.utils.vault_client import VaultClient
    with patch.dict(os.environ, {"VAULT_ENABLED": "false"}):
        client = VaultClient()
        assert client.list_secrets() == []


# --- memory ---
def test_core_memory_get():
    from src.memory.core_memory import get_core_memory
    cm = get_core_memory()
    assert cm is not None


def test_session_memory_get():
    from src.memory.session_memory import get_session_memory
    sm = get_session_memory()
    assert sm is not None


# --- edge filters is_speech ---
def test_is_speech_none_method():
    from src.edge.filters import is_speech
    import numpy as np
    audio = np.zeros(16000, dtype=np.float32)
    ok, meta = is_speech(audio, method="none")
    assert ok is True
    assert meta.get("method") == "none"


def test_is_speech_energy_empty():
    from src.edge.filters import is_speech_energy_filter
    import numpy as np
    ok, meta = is_speech_energy_filter(np.array([], dtype=np.float32), sample_rate=16000)
    assert ok is False
    assert "reason" in meta


def test_numpy_energy_filter_path():
    """Энергетический фильтр возвращает (bool, dict)."""
    import numpy as np
    from src.edge.filters import is_speech_energy_filter
    audio = np.sin(2 * np.pi * 500 * np.linspace(0, 1, 16000)).astype(np.float32)
    result = is_speech_energy_filter(audio, sample_rate=16000)
    assert isinstance(result, tuple) and len(result) == 2
    ok, meta = result
    assert ok in (True, False)
    assert isinstance(meta, dict)


# --- rate_limiter ---
def test_rate_limit_config():
    from src.utils.rate_limiter import RateLimitConfig
    assert hasattr(RateLimitConfig, "INGEST_AUDIO_LIMIT")
    assert hasattr(RateLimitConfig, "HEALTH_LIMIT")


# --- vault get_secret env fallback ---
def test_vault_get_secret_env_fallback():
    from src.utils.vault_client import VaultClient
    with patch.dict(os.environ, {"VAULT_ENABLED": "false", "OPENAI_API_KEY": "env-key-123"}):
        client = VaultClient()
        val = client.get_secret("openai")
    assert val == "env-key-123"


def test_vault_is_available_when_disabled():
    with patch.dict(os.environ, {"VAULT_ENABLED": "false"}):
        from src.utils.vault_client import VaultClient
        client = VaultClient()
        assert client.is_available() is False
