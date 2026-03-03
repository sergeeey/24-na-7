#!/usr/bin/env python3
"""
Миграция reflexio.db из plain SQLite → SQLCipher (AES-256-CBC).

Запуск (один раз на VPS):
    SQLCIPHER_KEY=<key> python scripts/migrate_to_sqlcipher.py

ПОЧЕМУ отдельный скрипт:
    Миграция необратима. Запускается вручную, один раз, с бэкапом.
    После миграции API читает БД только через sqlcipher3 + ключ из .env.
"""
import os
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

DB_PATH = Path("src/storage/reflexio.db")
BACKUP_PATH = Path(f"src/storage/reflexio.db.backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
ENCRYPTED_PATH = Path("src/storage/reflexio_encrypted.db")


def main() -> None:
    key = os.environ.get("SQLCIPHER_KEY", "")
    if not key:
        print("ERROR: SQLCIPHER_KEY не задан в окружении")
        sys.exit(1)

    if not DB_PATH.exists():
        print(f"ERROR: БД не найдена: {DB_PATH}")
        sys.exit(1)

    try:
        import sqlcipher3
    except ImportError:
        print("ERROR: sqlcipher3 не установлен. pip install sqlcipher3")
        sys.exit(1)

    # 1. Бэкап
    shutil.copy2(DB_PATH, BACKUP_PATH)
    print(f"[1/4] Бэкап сохранён: {BACKUP_PATH}")

    # 2. Создаём зашифрованную копию через sqlcipher_export.
    # ПОЧЕМУ sqlcipher_export вместо sqlite3.backup():
    #   backup() ожидает sqlite3.Connection, несовместим с sqlcipher3.
    #   sqlcipher_export — нативный метод SQLCipher: открываем plain (key=''),
    #   attach encrypted, экспортируем. Атомарно, на уровне страниц.
    plain_conn = sqlcipher3.connect(str(DB_PATH))
    plain_conn.execute("PRAGMA key = ''")  # пустой ключ = plain SQLite режим
    plain_conn.execute(f"ATTACH DATABASE '{ENCRYPTED_PATH}' AS encrypted KEY \"{key}\"")  # nosec B608
    plain_conn.execute("SELECT sqlcipher_export('encrypted')")
    plain_conn.execute("DETACH DATABASE encrypted")
    plain_conn.close()
    print(f"[2/4] Зашифрованная копия создана: {ENCRYPTED_PATH}")

    # 3. Верификация — открываем зашифрованную и считаем строки
    verify_conn = sqlcipher3.connect(str(ENCRYPTED_PATH))
    verify_conn.execute(f'PRAGMA key = "{key}"')  # nosec B608
    tables = verify_conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()
    table_names = [t[0] for t in tables]
    print(f"[3/4] Верификация: {len(table_names)} таблиц — {table_names}")
    verify_conn.close()

    # 4. Заменяем оригинал
    DB_PATH.rename(DB_PATH.with_suffix(".db.plain"))
    ENCRYPTED_PATH.rename(DB_PATH)
    print(f"[4/4] Готово! {DB_PATH} теперь зашифрован.")
    print(f"      Plain копия: {DB_PATH.with_suffix('.db.plain')}")
    print(f"      Бэкап:       {BACKUP_PATH}")
    print()
    print("Следующий шаг: docker restart reflexio-api")
    print("Убедись что SQLCIPHER_KEY задан в .env на VPS!")


if __name__ == "__main__":
    main()
