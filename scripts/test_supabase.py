#!/usr/bin/env python3
"""Тест подключения к Supabase."""
import os
import sys
from pathlib import Path

# Добавляем путь к проекту
sys.path.insert(0, str(Path(__file__).parent.parent))

# Устанавливаем переменные окружения если их нет
if not os.getenv("SUPABASE_URL"):
    os.environ["SUPABASE_URL"] = "https://lkmyliwjleegjkcgespp.supabase.co"

if not os.getenv("SUPABASE_ANON_KEY"):
    os.environ["SUPABASE_ANON_KEY"] = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImxrbXlsaXdqbGVlZ2prY2dlc3BwIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjIxOTAzNDEsImV4cCI6MjA3Nzc2NjM0MX0._SVPagOjW4uTjZclDk-5HihvlNY6s76wH8vLD5EyRlQ"

# Импортируем функцию проверки напрямую
import importlib.util
validator_path = Path(__file__).parent.parent / ".cursor" / "validation" / "mcp_validator.py"
spec = importlib.util.spec_from_file_location("mcp_validator", validator_path)
mcp_validator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mcp_validator)
ping_supabase = mcp_validator.ping_supabase

def main():
    """Запускает тест подключения к Supabase."""
    print("=" * 60)
    print("Тест подключения к Supabase")
    print("=" * 60)
    print(f"URL: {os.getenv('SUPABASE_URL')}")
    print(f"Key: {os.getenv('SUPABASE_ANON_KEY')[:20]}...")
    print()
    
    result = ping_supabase(os.getenv("SUPABASE_URL"), timeout=5)
    
    print(f"Статус: {result.get('status')}")
    if "latency_ms" in result:
        print(f"Задержка: {result['latency_ms']} мс")
    if "error" in result:
        print(f"Ошибка: {result['error']}")
    if "status_code" in result:
        print(f"HTTP код: {result['status_code']}")
    
    print()
    if result.get("status") == "ok":
        print("✅ Подключение успешно!")
        return 0
    else:
        print("❌ Подключение не удалось")
        return 1

if __name__ == "__main__":
    sys.exit(main())

