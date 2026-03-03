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

    # 2. Копируем schema + данные по таблицам.
    # ПОЧЕМУ не executescript: sqlcipher3.executescript() не flush'ит корректно,
    # файл создаётся но HMAC check fails при следующем открытии.
    # Надёжнее: DDL по одному execute(), данные через executemany() → commit().
    plain_conn = sqlite3.connect(str(DB_PATH))
    plain_conn.row_factory = sqlite3.Row

    if ENCRYPTED_PATH.exists():
        ENCRYPTED_PATH.unlink()

    enc_conn = sqlcipher3.connect(str(ENCRYPTED_PATH))
    enc_conn.execute(f'PRAGMA key = "{key}"')  # nosec B608
    enc_conn.execute("PRAGMA journal_mode = DELETE")  # WAL после полной записи

    # Копируем DDL (таблицы, индексы, триггеры)
    ddl_rows = plain_conn.execute(
        "SELECT sql FROM sqlite_master WHERE sql IS NOT NULL ORDER BY type DESC, name"
    ).fetchall()
    for row in ddl_rows:
        try:
            enc_conn.execute(row[0])
        except Exception:
            pass  # skip duplicates / virtual tables

    # Копируем данные по каждой таблице
    tables = plain_conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    ).fetchall()
    for (tbl_name,) in tables:
        rows = plain_conn.execute(f"SELECT * FROM \"{tbl_name}\"").fetchall()  # nosec B608 — table names from sqlite_master
        if not rows:
            continue
        cols_count = len(rows[0])
        placeholders = ",".join(["?" for _ in range(cols_count)])
        enc_conn.executemany(
            f"INSERT OR IGNORE INTO \"{tbl_name}\" VALUES ({placeholders})",  # nosec B608
            [tuple(r) for r in rows],
        )

    enc_conn.commit()
    enc_conn.close()
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
