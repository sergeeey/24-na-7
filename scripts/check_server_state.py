#!/usr/bin/env python3
"""Проверка состояния сервера: pipeline-status, БД, эндпоинты.
Запуск: python scripts/check_server_state.py
"""
import sys
from pathlib import Path

# Корень проекта
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.utils.config import settings
from src.api.routers.ingest import get_pipeline_status
import asyncio


def main():
    print("=== Reflexio: проверка сервера ===\n")

    # 1. Pipeline-status (как видит клиент)
    print("1. GET /ingest/pipeline-status (локальный вызов):")
    try:
        out = asyncio.run(get_pipeline_status())
        for k, v in out.items():
            print(f"   {k}: {v}")
    except Exception as e:
        print(f"   Ошибка: {e}")

    # 2. БД
    db_path = settings.STORAGE_PATH / "reflexio.db"
    print(f"\n2. БД: {db_path}")
    print(f"   Существует: {db_path.exists()}")
    if db_path.exists():
        from src.storage.db import get_reflexio_db
        db = get_reflexio_db(db_path)
        try:
            t = db.fetchone("SELECT COUNT(*) FROM transcriptions")[0]
            p = db.fetchone("SELECT COUNT(*) FROM ingest_queue WHERE status = 'pending'")[0]
            pr = db.fetchone("SELECT COUNT(*) FROM ingest_queue WHERE status = 'processed'")[0]
            e = db.fetchone("SELECT COUNT(*) FROM ingest_queue WHERE status = 'error'")[0]
            print(f"   transcriptions: {t}")
            print(f"   ingest_queue: pending={p}, processed={pr}, error={e}")
        except Exception as ex:
            print(f"   Ошибка запроса: {ex}")

    # 3. Что происходит на сервере при приёме с телефона
    print("\n3. Цепочка при приёме с телефона:")
    print("   Телефон -> WS /ws/ingest (binary WAV)")
    print("   -> verify_websocket_token (Authorization: Bearer <API_KEY>)")
    print("   -> _process_audio_segment -> process_audio_bytes (ASR, enrichment)")
    print("   -> ответы: type=received -> type=transcription | filtered | error")
    print("   GET /ingest/pipeline-status защищён auth_middleware: нужен заголовок Authorization: Bearer <API_KEY>.")

    print("\nГотово.")


if __name__ == "__main__":
    main()
