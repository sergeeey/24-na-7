@echo off
REM Запуск API сервера Reflexio 24/7 (Windows)

uvicorn src.api.main:app --reload --host 0.0.0.0 --port 8000

