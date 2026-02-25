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
