#!/usr/bin/env python3
"""Запрашивает с сервера Reflexio количество записей (транскрипций, фактов и т.д.).

Контролируемый тест пайплайна: после одной короткой записи (10–15 сек) проверьте
  curl -s -H "Authorization: Bearer $API_KEY" "$API_URL/ingest/pipeline-status"
  — вырос ли transcriptions_today, есть ли last_transcription_at.
"""
import os
import sys
from pathlib import Path

# Загружаем .env из корня проекта
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
except ImportError:
    pass

import requests


def _read_api_key_from_local_props() -> str:
    """Опционально читает SERVER_API_KEY из android/local.properties (для локальной проверки)."""
    try:
        p = Path(__file__).resolve().parents[1] / "android" / "local.properties"
        if not p.exists():
            return ""
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("SERVER_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"')
    except Exception:
        pass
    return ""


def main() -> None:
    api_url = os.getenv("API_URL", "https://reflexio247.duckdns.org").rstrip("/")
    api_key = os.getenv("API_KEY") or _read_api_key_from_local_props() or ""

    headers = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    try:
        r = requests.get(f"{api_url}/metrics", headers=headers, timeout=15)
        r.raise_for_status()
        data = r.json()
    except requests.RequestException as e:
        print(f"Ошибка запроса: {e}", file=sys.stderr)
        if hasattr(e, "response") and e.response is not None and e.response.status_code == 401:
            print("Подсказка: задайте API_KEY в .env или переменной окружения.", file=sys.stderr)
        sys.exit(1)

    db = data.get("database") or {}
    storage = data.get("storage") or {}
    transcriptions = db.get("transcriptions_count", 0)
    facts = db.get("facts_count", 0)
    uploads_wav = storage.get("uploads_count", 0)
    recordings_wav = storage.get("recordings_count", 0)
    queue_pending = db.get("ingest_queue_pending", 0)
    queue_processed = db.get("ingest_queue_processed", 0)
    queue_error = db.get("ingest_queue_error", 0)
    queue_filtered = db.get("ingest_queue_filtered", 0)

    print("Записи на сервере (reflexio247.duckdns.org):")
    print(f"  Транскрипций:     {transcriptions}")
    print(f"  Фактов/событий:   {facts}")
    print(f"  WAV в uploads:     {uploads_wav}")
    print(f"  WAV в recordings: {recordings_wav}")
    print("  Очередь ingest:")
    print(f"    pending:   {queue_pending}  (ожидают обработки)")
    print(f"    processed: {queue_processed}  (успешно)")
    print(f"    error:     {queue_error}  (ошибка ASR/пайплайна)")
    print(f"    filtered:  {queue_filtered}  (отфильтровано: шум/язык/спикер)")
    if queue_error > 0 and transcriptions == 0:
        print("\n  ⚠ Причина 0 транскрипций: сегменты падают с ошибкой (error). См. логи на VPS: journalctl -u reflexio-api -n 200 --no-pager")


if __name__ == "__main__":
    main()
