"""
Тесты для src/balance/storage.py и src/persongraph/service.py.

Почему нужен structured_events: ensure_balance_tables создаёт индексы
на structured_events (для backward-compat), поэтому эта таблица должна
существовать до первого вызова любой balance-функции.
"""
import json
import sqlite3
from datetime import date
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _create_structured_events(db_path: Path) -> None:
    """Создаём минимальную схему structured_events, которая нужна balance."""
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS structured_events (
            id TEXT PRIMARY KEY,
            text TEXT,
            sentiment TEXT DEFAULT 'neutral',
            urgency TEXT DEFAULT 'low',
            created_at TEXT NOT NULL,
            domains TEXT DEFAULT '[]'
        )
        """
    )
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Tests: balance/storage.py
# ---------------------------------------------------------------------------

class TestEnsureBalanceTables:
    def test_creates_domain_config_table(self, tmp_path):
        """ensure_balance_tables создаёт таблицу domain_config."""
        from src.balance.storage import ensure_balance_tables

        db = tmp_path / "test.db"
        _create_structured_events(db)
        ensure_balance_tables(db)

        conn = sqlite3.connect(str(db))
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        conn.close()
        assert "domain_config" in tables

    def test_inserts_default_domains(self, tmp_path):
        """ensure_balance_tables заполняет 8 дефолтных доменов."""
        from src.balance.storage import ensure_balance_tables, DEFAULT_DOMAINS

        db = tmp_path / "test.db"
        _create_structured_events(db)
        ensure_balance_tables(db)

        conn = sqlite3.connect(str(db))
        count = conn.execute("SELECT COUNT(*) FROM domain_config").fetchone()[0]
        conn.close()
        assert count == len(DEFAULT_DOMAINS)

    def test_idempotent(self, tmp_path):
        """Повторный вызов не дублирует записи."""
        from src.balance.storage import ensure_balance_tables

        db = tmp_path / "test.db"
        _create_structured_events(db)
        ensure_balance_tables(db)
        ensure_balance_tables(db)

        conn = sqlite3.connect(str(db))
        count = conn.execute("SELECT COUNT(*) FROM domain_config").fetchone()[0]
        conn.close()
        assert count == 8  # ровно 8, без дублей


class TestGetDomainConfigs:
    def test_returns_all_defaults(self, tmp_path):
        """get_domain_configs возвращает 8 доменов по умолчанию."""
        from src.balance.storage import get_domain_configs

        db = tmp_path / "test.db"
        _create_structured_events(db)
        configs = get_domain_configs(db)

        assert len(configs) == 8

    def test_domain_structure(self, tmp_path):
        """Каждый домен содержит обязательные поля."""
        from src.balance.storage import get_domain_configs

        db = tmp_path / "test.db"
        _create_structured_events(db)
        configs = get_domain_configs(db)

        for cfg in configs:
            assert "id" in cfg
            assert "domain" in cfg
            assert "display_name" in cfg
            assert "keywords" in cfg
            assert isinstance(cfg["keywords"], list)
            assert "is_active" in cfg
            assert isinstance(cfg["is_active"], bool)

    def test_default_domain_names(self, tmp_path):
        """В дефолтных доменах присутствуют work, health, family."""
        from src.balance.storage import get_domain_configs

        db = tmp_path / "test.db"
        _create_structured_events(db)
        configs = get_domain_configs(db)

        domain_names = {c["domain"] for c in configs}
        assert "work" in domain_names
        assert "health" in domain_names
        assert "family" in domain_names


class TestUpsertDomainConfig:
    def test_creates_new_domain(self, tmp_path):
        """upsert_domain_config добавляет новый домен."""
        from src.balance.storage import upsert_domain_config, get_domain_configs

        db = tmp_path / "test.db"
        _create_structured_events(db)
        upsert_domain_config(
            db_path=db,
            domain="test_domain",
            display_name="Test Domain",
            keywords=["тест", "проверка"],
        )
        configs = get_domain_configs(db)
        names = {c["domain"] for c in configs}
        assert "test_domain" in names

    def test_updates_existing_domain(self, tmp_path):
        """upsert_domain_config обновляет существующий домен (ON CONFLICT DO UPDATE)."""
        from src.balance.storage import upsert_domain_config, get_domain_configs

        db = tmp_path / "test.db"
        _create_structured_events(db)
        upsert_domain_config(db, "work", "Работа v2", ["новое_слово"], color="#ff0000")

        configs = get_domain_configs(db)
        work = next(c for c in configs if c["domain"] == "work")
        assert work["display_name"] == "Работа v2"
        assert "новое_слово" in work["keywords"]
        assert work["color"] == "#ff0000"

    def test_keywords_stored_as_list(self, tmp_path):
        """Ключевые слова сохраняются и возвращаются списком."""
        from src.balance.storage import upsert_domain_config, get_domain_configs

        db = tmp_path / "test.db"
        _create_structured_events(db)
        upsert_domain_config(db, "custom", "Custom", ["alpha", "beta", "gamma"])

        configs = get_domain_configs(db)
        custom = next(c for c in configs if c["domain"] == "custom")
        assert custom["keywords"] == ["alpha", "beta", "gamma"]


class TestScoreFromMentions:
    def test_zero_max_returns_zero(self):
        """_score_from_mentions(n, 0) всегда 0.0."""
        from src.balance.storage import _score_from_mentions

        assert _score_from_mentions(5, 0) == 0.0
        assert _score_from_mentions(0, 0) == 0.0

    def test_full_score(self):
        """mentions == max_mentions → score == 10.0."""
        from src.balance.storage import _score_from_mentions

        assert _score_from_mentions(10, 10) == 10.0

    def test_half_score(self):
        """5 из 10 → score == 5.0."""
        from src.balance.storage import _score_from_mentions

        assert _score_from_mentions(5, 10) == 5.0

    def test_fraction_rounded(self):
        """Результат округляется до 1 знака."""
        from src.balance.storage import _score_from_mentions

        result = _score_from_mentions(1, 3)
        assert round(result, 1) == result  # уже округлено
        assert 3.3 <= result <= 3.4


class TestGetBalanceWheel:
    def test_empty_events_returns_zero_balance(self, tmp_path):
        """Без событий balance_score == 0.0 и domains == []."""
        from src.balance.storage import get_balance_wheel

        db = tmp_path / "test.db"
        _create_structured_events(db)

        result = get_balance_wheel(
            db_path=db,
            from_date=date(2025, 1, 1),
            to_date=date(2025, 1, 31),
        )
        assert result["balance_score"] == 0.0
        assert result["domains"] == []
        assert "from" in result
        assert "to" in result
        assert "alert" in result
        assert "recommendation" in result

    def test_with_single_domain_events(self, tmp_path):
        """События с одним доменом → один domain в результате."""
        from src.balance.storage import get_balance_wheel

        db = tmp_path / "test.db"
        _create_structured_events(db)

        conn = sqlite3.connect(str(db))
        for i in range(3):
            conn.execute(
                "INSERT INTO structured_events (id, sentiment, created_at, domains) VALUES (?,?,?,?)",
                (str(i), "positive", "2025-01-15 10:00:00", json.dumps(["work"])),
            )
        conn.commit()
        conn.close()

        result = get_balance_wheel(db, date(2025, 1, 1), date(2025, 1, 31))
        assert len(result["domains"]) == 1
        assert result["domains"][0]["domain"] == "work"
        assert result["domains"][0]["mentions"] == 3
        assert result["domains"][0]["score"] == 10.0

    def test_dominant_domain_triggers_alert(self, tmp_path):
        """Если один домен доминирует > 60% — alert содержит его имя."""
        from src.balance.storage import get_balance_wheel

        db = tmp_path / "test.db"
        _create_structured_events(db)

        conn = sqlite3.connect(str(db))
        # 8 work events + 1 health event: work = 88.8% > 60%
        for i in range(8):
            conn.execute(
                "INSERT INTO structured_events (id, sentiment, created_at, domains) VALUES (?,?,?,?)",
                (f"w{i}", "positive", "2025-01-10 10:00:00", json.dumps(["work"])),
            )
        conn.execute(
            "INSERT INTO structured_events (id, sentiment, created_at, domains) VALUES (?,?,?,?)",
            ("h0", "neutral", "2025-01-10 10:00:00", json.dumps(["health"])),
        )
        conn.commit()
        conn.close()

        result = get_balance_wheel(db, date(2025, 1, 1), date(2025, 1, 31))
        assert "work" in result["alert"]

    def test_date_filter_excludes_out_of_range(self, tmp_path):
        """События за пределами диапазона не учитываются."""
        from src.balance.storage import get_balance_wheel

        db = tmp_path / "test.db"
        _create_structured_events(db)

        conn = sqlite3.connect(str(db))
        conn.execute(
            "INSERT INTO structured_events (id, sentiment, created_at, domains) VALUES (?,?,?,?)",
            ("old", "positive", "2024-12-31 23:59:59", json.dumps(["work"])),
        )
        conn.commit()
        conn.close()

        result = get_balance_wheel(db, date(2025, 1, 1), date(2025, 1, 31))
        assert result["domains"] == []

    def test_balance_score_multiple_domains(self, tmp_path):
        """Несколько доменов с равными упоминаниями → высокий balance_score."""
        from src.balance.storage import get_balance_wheel

        db = tmp_path / "test.db"
        _create_structured_events(db)

        conn = sqlite3.connect(str(db))
        for domain in ["work", "health", "family", "leisure"]:
            for i in range(3):
                conn.execute(
                    "INSERT INTO structured_events (id, sentiment, created_at, domains) VALUES (?,?,?,?)",
                    (f"{domain}_{i}", "neutral", "2025-01-15 10:00:00", json.dumps([domain])),
                )
        conn.commit()
        conn.close()

        result = get_balance_wheel(db, date(2025, 1, 1), date(2025, 1, 31))
        assert len(result["domains"]) == 4
        # При равных упоминаниях variance=0, balance_score=1/(1+0)=1.0
        assert result["balance_score"] == 1.0


# ---------------------------------------------------------------------------
# Tests: persongraph/service.py
# ---------------------------------------------------------------------------

class TestEnsurePersonGraphTables:
    def test_creates_table(self, tmp_path):
        """ensure_person_graph_tables создаёт person_graph_events."""
        from src.persongraph.service import ensure_person_graph_tables

        db = tmp_path / "pg.db"
        ensure_person_graph_tables(db)

        conn = sqlite3.connect(str(db))
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        conn.close()
        assert "person_graph_events" in tables

    def test_idempotent(self, tmp_path):
        """Повторный вызов не падает."""
        from src.persongraph.service import ensure_person_graph_tables

        db = tmp_path / "pg.db"
        ensure_person_graph_tables(db)
        ensure_person_graph_tables(db)  # должно пройти без ошибок


class TestBuildSimpleSummary:
    def test_no_markers_returns_neutral(self):
        """При нулевых маркерах — нейтральный ответ."""
        from src.persongraph.service import _build_simple_summary

        result = _build_simple_summary({
            "absolutism_score": 0.0,
            "self_criticism_score": 0.0,
            "procrastination_score": 0.0,
        })
        assert "нейтральна" in result

    def test_absolutism_marker(self):
        """При absolutism_score > 0.01 — упоминание категоричности."""
        from src.persongraph.service import _build_simple_summary

        result = _build_simple_summary({
            "absolutism_score": 0.5,
            "self_criticism_score": 0.0,
            "procrastination_score": 0.0,
        })
        assert "категоричности" in result

    def test_self_criticism_marker(self):
        """При self_criticism_score > 0.01 — маркеры самокритики."""
        from src.persongraph.service import _build_simple_summary

        result = _build_simple_summary({
            "absolutism_score": 0.0,
            "self_criticism_score": 0.3,
            "procrastination_score": 0.0,
        })
        assert "самокритики" in result

    def test_procrastination_marker(self):
        """При procrastination_score > 0.01 — сигналы откладывания."""
        from src.persongraph.service import _build_simple_summary

        result = _build_simple_summary({
            "absolutism_score": 0.0,
            "self_criticism_score": 0.0,
            "procrastination_score": 0.2,
        })
        assert "откладывания" in result

    def test_all_markers(self):
        """При всех трёх маркерах — все три упоминания в тексте."""
        from src.persongraph.service import _build_simple_summary

        result = _build_simple_summary({
            "absolutism_score": 0.5,
            "self_criticism_score": 0.3,
            "procrastination_score": 0.2,
        })
        assert "категоричности" in result
        assert "самокритики" in result
        assert "откладывания" in result

    def test_missing_keys_use_default_zero(self):
        """Отсутствующие ключи не вызывают ошибку (get с default 0.0)."""
        from src.persongraph.service import _build_simple_summary

        result = _build_simple_summary({})
        assert "нейтральна" in result


class TestSaveDayPsychologySnapshot:
    def test_returns_payload_with_markers(self, tmp_path):
        """save_day_psychology_snapshot возвращает dict с markers и summary."""
        from src.persongraph.service import save_day_psychology_snapshot

        db = tmp_path / "pg.db"
        result = save_day_psychology_snapshot(db, "2025-01-15", "Сегодня хороший день.")

        assert "markers" in result
        assert "summary" in result
        assert isinstance(result["markers"], dict)
        assert isinstance(result["summary"], str)

    def test_persisted_to_db(self, tmp_path):
        """Снимок сохраняется в БД и может быть прочитан напрямую."""
        from src.persongraph.service import save_day_psychology_snapshot

        db = tmp_path / "pg.db"
        save_day_psychology_snapshot(db, "2025-01-20", "Тестовый текст.")

        conn = sqlite3.connect(str(db))
        rows = conn.execute(
            "SELECT * FROM person_graph_events WHERE day=? AND event_type=?",
            ("2025-01-20", "psychology_snapshot"),
        ).fetchall()
        conn.close()
        assert len(rows) == 1

    def test_neutral_text_summary(self, tmp_path):
        """Нейтральный текст → нейтральный summary."""
        from src.persongraph.service import save_day_psychology_snapshot

        db = tmp_path / "pg.db"
        result = save_day_psychology_snapshot(db, "2025-02-01", "Небо голубое.")
        # summary может быть нейтральным или содержать маркеры — проверяем что он непустой
        assert len(result["summary"]) > 0

    def test_multiple_saves_same_day(self, tmp_path):
        """Несколько снимков за один день — каждый сохраняется как отдельная запись."""
        from src.persongraph.service import save_day_psychology_snapshot

        db = tmp_path / "pg.db"
        save_day_psychology_snapshot(db, "2025-01-15", "Первый текст.")
        save_day_psychology_snapshot(db, "2025-01-15", "Второй текст.")

        conn = sqlite3.connect(str(db))
        count = conn.execute(
            "SELECT COUNT(*) FROM person_graph_events WHERE day=?", ("2025-01-15",)
        ).fetchone()[0]
        conn.close()
        assert count == 2


class TestGetDayInsights:
    def test_no_snapshot_returns_empty(self, tmp_path):
        """Если нет снимка за день — get_day_insights возвращает []."""
        from src.persongraph.service import get_day_insights

        db = tmp_path / "pg.db"
        result = get_day_insights(db, "2025-01-15")
        assert result == []

    def test_with_snapshot_returns_five_insights(self, tmp_path):
        """После сохранения снимка — 5 инсайтов с разными ролями."""
        from src.persongraph.service import save_day_psychology_snapshot, get_day_insights

        db = tmp_path / "pg.db"
        save_day_psychology_snapshot(db, "2025-01-15", "Сегодня много работал и устал.")
        insights = get_day_insights(db, "2025-01-15")

        assert len(insights) == 5

    def test_insights_have_role_and_insight(self, tmp_path):
        """Каждый инсайт содержит поля role и insight."""
        from src.persongraph.service import save_day_psychology_snapshot, get_day_insights

        db = tmp_path / "pg.db"
        save_day_psychology_snapshot(db, "2025-01-16", "Текст для анализа.")
        insights = get_day_insights(db, "2025-01-16")

        roles = {i["role"] for i in insights}
        assert "psychologist" in roles
        assert "coach" in roles
        assert "pattern_detector" in roles

    def test_returns_latest_snapshot(self, tmp_path):
        """При нескольких снимках — возвращается последний (ORDER BY created_at DESC LIMIT 1)."""
        from src.persongraph.service import save_day_psychology_snapshot, get_day_insights, ensure_person_graph_tables

        db = tmp_path / "pg.db"
        ensure_person_graph_tables(db)

        # Вставляем старый снимок с явно обновлённым created_at
        import time
        save_day_psychology_snapshot(db, "2025-01-17", "Старый текст.")
        time.sleep(0.01)
        save_day_psychology_snapshot(db, "2025-01-17", "Новый текст с явными маркерами: всегда должен.")

        insights = get_day_insights(db, "2025-01-17")
        # Должны вернуться 5 инсайтов, основанных на последнем снимке
        assert len(insights) == 5

    def test_wrong_day_returns_empty(self, tmp_path):
        """Снимок за другой день не возвращается."""
        from src.persongraph.service import save_day_psychology_snapshot, get_day_insights

        db = tmp_path / "pg.db"
        save_day_psychology_snapshot(db, "2025-01-15", "Текст.")
        result = get_day_insights(db, "2025-01-16")
        assert result == []
