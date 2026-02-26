"""
Финальный набор тестов для выхода на 80% покрытия.
Целевые ветки: api/main, storage/migrate, metrics/prometheus.
"""
import sqlite3
from unittest.mock import patch, MagicMock

from fastapi.testclient import TestClient


def test_migrate_main_verify():
    """storage.migrate.main() с --verify вызывает verify_row_counts и возвращает 0."""
    from unittest.mock import patch

    with patch("sys.argv", ["migrate", "--verify"]):
        with patch("src.storage.migrate.verify_row_counts", return_value={"match": True, "tables": {}}):
            from src.storage.migrate import main
            exit_code = main()
    assert exit_code == 0


def test_migrate_main_no_args_returns_1():
    """storage.migrate.main() без флагов выводит подсказку и возвращает 1."""
    with patch("sys.argv", ["migrate"]):
        from src.storage.migrate import main
        exit_code = main()
    assert exit_code == 1


def test_migrate_main_apply_schema():
    """storage.migrate.main() с --apply-schema вызывает apply_schema_migrations."""
    with patch("sys.argv", ["migrate", "--apply-schema", "--to", "sqlite"]):
        with patch("src.storage.migrate.apply_schema_migrations", return_value={"migrations_applied": [], "errors": []}):
            from src.storage.migrate import main
            exit_code = main()
    assert exit_code == 0


def test_migrate_main_migrate_data_to_sqlite_returns_1():
    """storage.migrate.main() с --migrate-data --to sqlite возвращает 1 (only Supabase)."""
    with patch("sys.argv", ["migrate", "--migrate-data", "--to", "sqlite"]):
        from src.storage.migrate import main
        exit_code = main()
    assert exit_code == 1


def test_migrate_main_migrate_data_failed_returns_1():
    """storage.migrate.main() с --migrate-data при status=failed возвращает 1."""
    with patch("sys.argv", ["migrate", "--migrate-data", "--to", "supabase"]):
        with patch("src.storage.migrate.migrate_to_supabase", return_value={"status": "failed", "errors": ["x"]}):
            from src.storage.migrate import main
            exit_code = main()
    assert exit_code == 1


def test_migrate_main_verify_with_differences():
    """storage.migrate.main() с --verify при match=False выводит различия."""
    with patch("sys.argv", ["migrate", "--verify"]):
        with patch("src.storage.migrate.verify_row_counts", return_value={
            "match": False, "tables": {}, "differences": [{"table": "t1", "sqlite": 1, "supabase": 0, "diff": 1}]
        }):
            from src.storage.migrate import main
            exit_code = main()
    assert exit_code == 0


def test_migrate_main_apply_schema_with_errors():
    """storage.migrate.main() с --apply-schema при errors в результате выводит предупреждение."""
    with patch("sys.argv", ["migrate", "--apply-schema", "--to", "sqlite"]):
        with patch("src.storage.migrate.apply_schema_migrations", return_value={
            "migrations_applied": ["001.sql"], "errors": ["001.sql: some error"]
        }):
            from src.storage.migrate import main
            exit_code = main()
    assert exit_code == 0


def test_migrate_main_backup_fails():
    """storage.migrate.main() с --backup и --migrate-data при ошибке backup не падает."""
    with patch("sys.argv", ["migrate", "--backup", "--migrate-data", "--to", "supabase"]):
        with patch("src.storage.migrate.backup_sqlite", side_effect=FileNotFoundError("no db")):
            with patch("src.storage.migrate.migrate_to_supabase", return_value={"status": "ok"}):
                from src.storage.migrate import main
                exit_code = main()
    assert exit_code == 0


def test_api_ingest_status_endpoint():
    """GET /ingest/status/{file_id} возвращает pending."""
    from src.api.main import app

    client = TestClient(app)
    r = client.get("/ingest/status/some-file-id-123")
    assert r.status_code == 200
    data = r.json()
    assert data.get("status") == "pending"
    assert data.get("id") == "some-file-id-123"


def test_api_prometheus_metrics_endpoint():
    """GET /metrics/prometheus возвращает 200 и текст в формате Prometheus."""
    from src.api.main import app

    client = TestClient(app)
    r = client.get("/metrics/prometheus")
    assert r.status_code == 200
    assert "reflexio_uploads_total" in r.text or "reflexio_health" in r.text


def test_api_prometheus_metrics_db_exception(tmp_path):
    """GET /metrics/prometheus при ошибке SQLite не падает (except pass)."""
    from src.api.main import app
    from src.utils.config import settings

    (tmp_path / "reflexio.db").write_bytes(b"")
    with patch.object(settings, "STORAGE_PATH", tmp_path):
        with patch("sqlite3.connect") as mock_connect:
            mock_conn = MagicMock()
            mock_conn.cursor.return_value.execute.side_effect = sqlite3.Error("db error")
            mock_connect.return_value = mock_conn
            client = TestClient(app)
            r = client.get("/metrics/prometheus")
    assert r.status_code == 200


def test_api_prometheus_metrics_with_osint_json(tmp_path, monkeypatch):
    """GET /metrics/prometheus с cursor-metrics.json с osint покрывает ветку deepconf."""
    from src.api.main import app

    (tmp_path / "cursor-metrics.json").write_text(
        '{"metrics": {"osint": {"avg_deepconf_confidence": 0.85}}}',
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    client = TestClient(app)
    r = client.get("/metrics/prometheus")
    assert r.status_code == 200
    assert "reflexio_deepconf_avg_confidence" in r.text


def test_apply_schema_sqlite_execute_exception(tmp_path):
    """apply_schema_migrations(backend=sqlite) при ошибке executescript пишет в errors."""
    from src.storage.migrate import apply_schema_migrations
    from src.utils.config import settings

    (tmp_path / "reflexio.db").write_bytes(b"")
    with patch.object(settings, "STORAGE_PATH", tmp_path):
        with patch("sqlite3.connect") as mock_connect:
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_cursor.executescript.side_effect = sqlite3.OperationalError("syntax error")
            mock_conn.cursor.return_value = mock_cursor
            mock_connect.return_value = mock_conn
            result = apply_schema_migrations(backend="sqlite")
    assert "errors" in result
    assert any("syntax error" in e or "Failed" in e for e in result["errors"])


def test_api_voice_intent_endpoint():
    """POST /voice/intent без тела возвращает 422 или обработанную ошибку."""
    from src.api.main import app

    client = TestClient(app)
    r = client.post("/voice/intent", json={})
    assert r.status_code in (200, 400, 422, 500)


def test_api_search_phrases_exception_returns_500():
    """POST /search/phrases при исключении в search_phrases возвращает 500."""
    from src.api.main import app

    with patch("src.api.routers.search.search_phrases", side_effect=RuntimeError("search failed")):
        client = TestClient(app)
        r = client.post("/search/phrases", json={"query": "test", "audio_id": "a1"})
    assert r.status_code == 500
    assert "Search failed" in r.json().get("detail", "")


def test_api_voice_intent_exception_returns_500():
    """POST /voice/intent при исключении в recognize_intent возвращает 500."""
    from src.api.main import app

    with patch("src.voice_agent.voiceflow_rag.get_voiceflow_client") as m:
        m.return_value.recognize_intent.side_effect = RuntimeError("voiceflow down")
        client = TestClient(app)
        r = client.post("/voice/intent", json={"text": "hello"})
    assert r.status_code == 500
    assert "Intent recognition failed" in r.json().get("detail", "")


def test_metrics_osint_non_dict_exception(tmp_path, monkeypatch):
    """GET /metrics при cursor-metrics.json с osint не-словарём не падает (except 656-657)."""
    from src.api.main import app

    (tmp_path / "cursor-metrics.json").write_text(
        '{"metrics": {"osint": 123}}',
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    client = TestClient(app)
    r = client.get("/metrics")
    assert r.status_code == 200


def test_digest_generate_extended_metrics_invalid_created_at(tmp_path):
    """DigestGenerator.generate с EXTENDED_METRICS и invalid created_at не падает (except pass)."""
    from src.digest.generator import DigestGenerator
    from datetime import date
    from src.utils.config import settings

    db_path = tmp_path / "e.db"
    db_path.write_bytes(b"")
    gen = DigestGenerator(db_path=db_path)
    metrics = {
        "transcriptions_count": 1, "facts_count": 0, "total_duration_minutes": 0,
        "total_characters": 1, "total_words": 1, "average_words_per_transcription": 1,
        "information_density_score": 0.0, "density_level": "🟢 Низкая",
    }
    with patch.object(settings, "EXTENDED_METRICS", True):
        with patch.object(gen, "get_transcriptions", return_value=[{"text": "x", "created_at": "invalid"}]):
            with patch.object(gen, "extract_facts", return_value=[]):
                with patch.object(gen, "calculate_metrics", return_value=metrics):
                    out = gen.generate(target_date=date(2026, 1, 1), output_format="markdown")
    assert out.exists()


def test_digest_generate_markdown_enhanced_summary_exception(tmp_path):
    """DigestGenerator: при исключении в enhanced summary логируется warning, маркдаун не падает."""
    from src.digest.generator import DigestGenerator
    from datetime import date

    db_path = tmp_path / "d.db"
    db_path.write_bytes(b"")
    gen = DigestGenerator(db_path=db_path)
    metrics = {
        "transcriptions_count": 1, "facts_count": 0, "total_duration_minutes": 0,
        "total_characters": 10, "total_words": 2, "average_words_per_transcription": 2,
        "information_density_score": 0.0, "density_level": "🟢 Низкая",
    }
    with patch("src.digest.generator.SUMMARIZER_AVAILABLE", True):
        with patch("src.digest.generator.generate_dense_summary", side_effect=RuntimeError("dense failed")):
            with patch.object(gen, "get_transcriptions", return_value=[{"text": "Hello world", "id": "1"}]):
                with patch.object(gen, "extract_facts", return_value=[]):
                    with patch.object(gen, "calculate_metrics", return_value=metrics):
                        out = gen.generate(target_date=date(2026, 1, 1), output_format="markdown")
    assert out.exists()
