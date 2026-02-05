"""
Точка входа приложения Reflexio (uvicorn src.reflexio.main:app).
Реэкспорт FastAPI app из src.api.main для совместимости с интеграцией Golos.
"""
from src.api.main import app

__all__ = ["app"]
