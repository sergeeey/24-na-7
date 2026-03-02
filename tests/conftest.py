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
