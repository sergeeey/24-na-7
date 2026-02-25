param()

$ErrorActionPreference = "Stop"

Write-Host "Running smoke checks..."
python -m pytest -q tests/test_api.py tests/test_memory_audit_api.py
python -m pytest -q tests/test_websocket.py
ruff check src tests

Write-Host "Done"
