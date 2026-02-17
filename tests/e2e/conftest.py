"""Фикстуры для E2E тестов."""
import pytest
import tempfile
import sqlite3
from pathlib import Path
from fastapi.testclient import TestClient

from src.api.main import app


@pytest.fixture
def test_db(tmp_path):
    """Создаёт тестовую БД."""
    db_path = tmp_path / "test_reflexio.db"
    conn = sqlite3.connect(str(db_path))
    
    # Создаём таблицы
    conn.execute("""
        CREATE TABLE IF NOT EXISTS ingest_queue (
            id TEXT PRIMARY KEY,
            filename TEXT NOT NULL,
            file_path TEXT NOT NULL,
            file_size INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT,
            processed_at TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS transcriptions (
            id TEXT PRIMARY KEY,
            ingest_id TEXT NOT NULL,
            text TEXT NOT NULL,
            language TEXT,
            duration REAL,
            segments TEXT,
            created_at TEXT
        )
    """)
    conn.commit()
    conn.close()
    
    return db_path


@pytest.fixture
def client():
    """Создаёт тестовый клиент FastAPI."""
    return TestClient(app)
