"""
Тесты для доведения покрытия storage/migrate до 80%.
Ветки исключений в verify_row_counts, apply_schema.
"""
import sqlite3
import pytest
from unittest.mock import patch, MagicMock


def test_verify_row_counts_table_exception(tmp_path):
    """verify_row_counts: исключение при проверке одной из таблиц попадает в except и пишет error в result."""
    from src.storage.migrate import verify_row_counts
    from src.utils.config import settings

    db_path = tmp_path / "reflexio.db"
    conn = sqlite3.connect(str(db_path))
    for t in ["missions", "claims", "audio_meta", "text_entries", "insights", "metrics",
              "ingest_queue", "transcriptions", "facts", "digests"]:
        conn.execute(f"CREATE TABLE IF NOT EXISTS {t} (id TEXT)")
    conn.commit()
    conn.close()

    mock_supabase = MagicMock()
    call_count = [0]

    def execute_side_effect(*args, **kwargs):
        call_count[0] += 1
        if call_count[0] == 1:
            return MagicMock(count=0, data=[])
        raise RuntimeError("Supabase error")

    chain = mock_supabase.table.return_value.select.return_value.limit.return_value
    chain.execute.side_effect = execute_side_effect

    with patch.object(settings, "STORAGE_PATH", tmp_path):
        with patch("src.storage.supabase_client.get_supabase_client", return_value=mock_supabase):
            result = verify_row_counts()
    assert "tables" in result
    assert any(
        isinstance(t, dict) and t.get("error") for t in result["tables"].values()
    ), "at least one table should have error from Supabase exception"


def test_verify_row_counts_connect_raises(tmp_path):
    """verify_row_counts: при падении sqlite3.connect срабатывает внешний except, result['error'] задаётся."""
    from src.storage.migrate import verify_row_counts
    from src.utils.config import settings

    (tmp_path / "reflexio.db").write_bytes(b"not a db")
    with patch.object(settings, "STORAGE_PATH", tmp_path):
        with patch("sqlite3.connect", side_effect=RuntimeError("disk error")):
            result = verify_row_counts()
    assert "error" in result
    assert "disk error" in result["error"]


def test_backup_sqlite_not_found_raises(tmp_path):
    """backup_sqlite при отсутствии БД бросает FileNotFoundError."""
    from src.storage.migrate import backup_sqlite
    from src.utils.config import settings

    with patch.object(settings, "STORAGE_PATH", tmp_path):
        with pytest.raises(FileNotFoundError, match="not found"):
            backup_sqlite()




def test_apply_schema_migrations_no_migration_files(tmp_path):
    """apply_schema_migrations: при отсутствии .sql в migrations возвращает errors."""
    import src.storage.migrate as migrate_mod
    from src.storage.migrate import apply_schema_migrations

    (tmp_path / "storage" / "migrations").mkdir(parents=True)
    with patch.object(migrate_mod, "__file__", str(tmp_path / "storage" / "migrate.py")):
        result = apply_schema_migrations(backend="sqlite")
    assert result.get("errors") and any("No migration" in e for e in result["errors"])


def test_migrate_to_supabase_sqlite_not_found(tmp_path):
    """migrate_to_supabase возвращает failed когда SQLite БД нет."""
    from src.storage.migrate import migrate_to_supabase
    from src.utils.config import settings

    with patch.object(settings, "STORAGE_PATH", tmp_path):
        with patch("src.storage.supabase_client.test_connection", return_value={"status": "ok"}):
            with patch("src.storage.supabase_client.get_supabase_client", return_value=MagicMock()):
                result = migrate_to_supabase(dry_run=False)
    assert result["status"] == "failed"
    assert any("not found" in e.lower() or "sqlite" in e.lower() for e in result.get("errors", []))
