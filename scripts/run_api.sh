#!/bin/bash
# Запуск API сервера Reflexio 24/7

uvicorn src.api.main:app --reload --host 0.0.0.0 --port 8000

