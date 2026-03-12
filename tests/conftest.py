"""Root conftest — общие фикстуры для всех тестов Reflexio.

ПОЧЕМУ: тесты проверяют бизнес-логику, а не auth middleware.
Auth middleware тестируется отдельно (test_integration_security.py).
В тестовой среде API_KEY=None восстанавливает fail-open поведение
и позволяет всем тестам работать без заголовков авторизации.
"""
import pytest


@pytest.fixture(autouse=True, scope="session")
def disable_auth_for_tests():
    """Отключает auth для всего test suite.

    ПОЧЕМУ scope="session": настраивается один раз на всю сессию,
    а не пересоздаётся для каждого теста — экономит время.
    Если нужно тестировать auth отдельно, используй patch внутри теста.
    """
    from src.utils.config import settings

    original = settings.API_KEY
    # object.__setattr__ обходит pydantic frozen model protection
    object.__setattr__(settings, "API_KEY", None)
    yield
    object.__setattr__(settings, "API_KEY", original)


@pytest.fixture(autouse=True)
def _clean_reflexio_db_singletons():
    """Очищает ReflexioDB singleton cache между тестами.

    ПОЧЕМУ: ReflexioDB._instances — class-level dict, который переживает тесты.
    Каждый тест использует уникальный tmp_path, но stale instances с thread-local
    connections к удалённым temp-базам могут сбивать sqlite3 module internal state.
    """
    from src.storage.db import ReflexioDB

    yield
    # Закрываем все thread-local connections перед очисткой
    for instance in ReflexioDB._instances.values():
        instance.close_thread_connection()
    ReflexioDB._instances.clear()


@pytest.fixture(autouse=True)
def _reset_rate_limiter_storage():
    """Сбрасывает in-memory rate limiter между тестами.

    ПОЧЕМУ: весь suite использует один app singleton, а slowapi memory backend
    хранит counters между TestClient instances. Без reset поздние тесты по
    /ingest/audio начинают падать на 429 из-за предыдущих запросов.
    """
    try:
        from src.api.main import app
        from src.api.routers import admin
        from src.api.routers import analyze
        from src.api.routers import asr
        from src.api.routers import audit
        from src.api.routers import balance
        from src.api.routers import commitments
        from src.api.routers import compliance
        from src.api.routers import digest
        from src.api.routers import graph
        from src.api.routers import health_metrics
        from src.api.routers import ingest
        from src.api.routers import memory
        from src.api.routers import metrics
        from src.api.routers import query
        from src.api.routers import search
        from src.api.routers import voice

        limiters = [
            getattr(app.state, "limiter", None),
            getattr(admin, "limiter", None),
            getattr(analyze, "limiter", None),
            getattr(asr, "limiter", None),
            getattr(audit, "limiter", None),
            getattr(balance, "limiter", None),
            getattr(commitments, "limiter", None),
            getattr(compliance, "limiter", None),
            getattr(digest, "limiter", None),
            getattr(graph, "limiter", None),
            getattr(health_metrics, "limiter", None),
            getattr(ingest, "limiter", None),
            getattr(memory, "limiter", None),
            getattr(metrics, "limiter", None),
            getattr(query, "limiter", None),
            getattr(search, "limiter", None),
            getattr(voice, "limiter", None),
        ]

        def _reset(limiters_to_reset):
            for limiter in limiters_to_reset:
                storage = getattr(limiter, "_storage", None)
                if storage is not None and hasattr(storage, "reset"):
                    storage.reset()

        _reset(limiters)
        yield
        _reset(limiters)
    except Exception:
        yield
