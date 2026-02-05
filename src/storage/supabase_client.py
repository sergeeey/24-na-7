"""Клиент для работы с Supabase."""
import os
from typing import Optional, Dict, Any
from pathlib import Path

try:
    from supabase import create_client, Client
    HAS_SUPABASE = True
except ImportError:
    HAS_SUPABASE = False
    Client = None


def get_supabase_client() -> Optional[Client]:
    """
    Создаёт и возвращает клиент Supabase.
    
    Returns:
        Клиент Supabase или None, если не настроен
    """
    if not HAS_SUPABASE:
        return None
    
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_ANON_KEY") or os.getenv("SUPABASE_SERVICE_KEY")
    
    if not supabase_url or not supabase_key:
        return None
    
    try:
        return create_client(supabase_url, supabase_key)
    except Exception:
        return None


def test_connection() -> Dict[str, Any]:
    """
    Проверяет подключение к Supabase.
    
    Returns:
        Словарь с результатами проверки
    """
    if not HAS_SUPABASE:
        return {
            "status": "error",
            "error": "supabase library not installed. Run: pip install supabase"
        }
    
    client = get_supabase_client()
    
    if not client:
        return {
            "status": "error",
            "error": "Supabase not configured. Set SUPABASE_URL and SUPABASE_ANON_KEY"
        }
    
    try:
        # Простая проверка через запрос к базе данных
        response = client.table("_health").select("status").limit(1).execute()
        return {
            "status": "ok",
            "message": "Supabase connection successful"
        }
    except Exception as e:
        # Если таблицы _health нет, пробуем просто подключиться
        try:
            # Пробуем запрос к REST API
            import requests
            response = requests.get(
                f"{os.getenv('SUPABASE_URL')}/rest/v1/",
                headers={"apikey": os.getenv("SUPABASE_ANON_KEY", "")},
                timeout=5
            )
            if response.status_code in (200, 401):
                return {
                    "status": "ok",
                    "message": "Supabase API accessible"
                }
            else:
                return {
                    "status": "warn",
                    "message": f"Supabase responded with status {response.status_code}"
                }
        except Exception as e2:
            return {
                "status": "error",
                "error": str(e2)
            }


if __name__ == "__main__":
    """Тест подключения к Supabase."""
    result = test_connection()
    print(f"Status: {result.get('status')}")
    if "error" in result:
        print(f"Error: {result['error']}")
    elif "message" in result:
        print(f"Message: {result['message']}")











