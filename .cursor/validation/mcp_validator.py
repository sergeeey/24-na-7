"""
MCP Integration Validator — проверка состояния и здоровья MCP-сервисов.

Измеряет латентность, проверяет доступность и собирает метрики для Governance Loop.
"""
import json
import os
import subprocess
import time
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any

# Добавляем путь к проекту
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False


MCP_FILE = Path(".cursor/mcp.json")
REPORT_FILE = Path(".cursor/metrics/mcp_health.json")
METRICS_DIR = Path(".cursor/metrics")


def ping_supabase(uri: str, timeout: int = 2) -> Dict[str, Any]:
    """Проверяет доступность Supabase."""
    if not HAS_REQUESTS:
        return {"status": "error", "error": "requests library not available"}
    
    start = time.time()
    try:
        supabase_url = os.getenv("SUPABASE_URL", "")
        if not supabase_url:
            return {"status": "disabled", "latency_ms": None, "reason": "SUPABASE_URL not set"}
        
        # Проверяем health endpoint или базовый REST endpoint
        health_url = f"{supabase_url.rstrip('/')}/rest/v1/"
        response = requests.get(health_url, timeout=timeout, headers={
            "apikey": os.getenv("SUPABASE_ANON_KEY", ""),
        })
        
        latency = round((time.time() - start) * 1000, 2)
        
        if response.status_code in (200, 401):  # 401 означает что сервис доступен, просто нужна авторизация
            return {"status": "ok", "latency_ms": latency}
        else:
            return {"status": "warn", "latency_ms": latency, "status_code": response.status_code}
            
    except requests.exceptions.Timeout:
        return {"status": "fail", "error": "timeout", "latency_ms": round((time.time() - start) * 1000, 2)}
    except requests.exceptions.RequestException as e:
        return {"status": "fail", "error": str(e), "latency_ms": round((time.time() - start) * 1000, 2)}
    except Exception as e:
        return {"status": "error", "error": str(e)}


def ping_github(cfg: Dict, timeout: int = 2) -> Dict[str, Any]:
    """Проверяет доступность GitHub CLI."""
    start = time.time()
    try:
        # Проверяем доступность gh CLI
        result = subprocess.run(
            ["gh", "auth", "status"],
            capture_output=True,
            timeout=timeout,
            text=True,
        )
        
        latency = round((time.time() - start) * 1000, 2)
        
        if result.returncode == 0:
            return {"status": "ok", "latency_ms": latency}
        else:
            return {"status": "fail", "error": "gh CLI not authenticated", "latency_ms": latency}
            
    except subprocess.TimeoutExpired:
        return {"status": "fail", "error": "timeout", "latency_ms": round((time.time() - start) * 1000, 2)}
    except FileNotFoundError:
        return {"status": "disabled", "error": "gh CLI not installed", "latency_ms": None}
    except Exception as e:
        return {"status": "error", "error": str(e)}


def ping_docker(cfg: Dict, timeout: int = 2) -> Dict[str, Any]:
    """Проверяет доступность Docker."""
    start = time.time()
    try:
        # Простая проверка через docker ps
        result = subprocess.run(
            ["docker", "ps", "--format", "{{.ID}}"],
            capture_output=True,
            timeout=timeout,
            text=True,
        )
        
        latency = round((time.time() - start) * 1000, 2)
        
        if result.returncode == 0:
            return {"status": "ok", "latency_ms": latency}
        else:
            return {"status": "fail", "error": "docker not available", "latency_ms": latency}
            
    except subprocess.TimeoutExpired:
        return {"status": "fail", "error": "timeout", "latency_ms": round((time.time() - start) * 1000, 2)}
    except FileNotFoundError:
        return {"status": "disabled", "error": "docker not installed", "latency_ms": None}
    except Exception as e:
        return {"status": "error", "error": str(e)}


def ping_brave(cfg: Dict, timeout: int = 2) -> Dict[str, Any]:
    """Проверяет доступность Brave Search API."""
    if not HAS_REQUESTS:
        return {"status": "error", "error": "requests library not available"}
    
    start = time.time()
    try:
        api_key = os.getenv("BRAVE_API_KEY")
        if not api_key:
            return {"status": "disabled", "error": "BRAVE_API_KEY not set", "latency_ms": None}
        
        # Простая проверка через test запрос
        import requests
        headers = {"X-Subscription-Token": api_key, "Accept": "application/json"}
        response = requests.get(
            "https://api.search.brave.com/res/v1/web/search",
            params={"q": "test", "count": 1},
            headers=headers,
            timeout=timeout,
        )
        
        latency = round((time.time() - start) * 1000, 2)
        
        if response.status_code == 200:
            return {"status": "ok", "latency_ms": latency}
        elif response.status_code == 401:
            return {"status": "fail", "error": "Invalid API key", "latency_ms": latency}
        else:
            return {"status": "warn", "latency_ms": latency, "status_code": response.status_code}
            
    except requests.exceptions.Timeout:
        return {"status": "fail", "error": "timeout", "latency_ms": round((time.time() - start) * 1000, 2)}
    except Exception as e:
        return {"status": "error", "error": str(e)}


def ping_brightdata(cfg: Dict, timeout: int = 5) -> Dict[str, Any]:
    """Проверяет доступность Bright Data (proxy или API)."""
    if not HAS_REQUESTS:
        return {"status": "error", "error": "requests library not available"}
    
    start = time.time()
    try:
        import requests
        
        # Приоритет: проверяем proxy (если доступен)
        proxy_http = os.getenv("BRIGHTDATA_PROXY_HTTP")
        if proxy_http:
            try:
                proxies = {"http": proxy_http, "https": proxy_http}
                response = requests.get(
                    "https://api.ipify.org?format=json",
                    proxies=proxies,
                    timeout=timeout,
                )
                latency = round((time.time() - start) * 1000, 2)
                
                if response.status_code == 200:
                    data = response.json()
                    ip = data.get("ip", "unknown")
                    return {"status": "ok", "latency_ms": latency, "proxy_ip": ip, "method": "proxy"}
                else:
                    return {"status": "warn", "latency_ms": latency, "status_code": response.status_code, "method": "proxy"}
            except requests.exceptions.ProxyError:
                return {"status": "fail", "error": "proxy authentication failed", "latency_ms": round((time.time() - start) * 1000, 2)}
            except requests.exceptions.Timeout:
                return {"status": "fail", "error": "proxy timeout", "latency_ms": round((time.time() - start) * 1000, 2)}
        
        # Fallback: проверяем API key
        api_key = os.getenv("BRIGHTDATA_API_KEY")
        if not api_key:
            return {"status": "disabled", "error": "BRIGHTDATA_API_KEY or BRIGHTDATA_PROXY_HTTP not set", "latency_ms": None}
        
        headers = {"Authorization": f"Bearer {api_key}"}
        
        response = requests.get(
            "https://api.brightdata.com/health",
            headers=headers,
            timeout=timeout,
        )
        
        latency = round((time.time() - start) * 1000, 2)
        
        if response.status_code in (200, 401):
            return {"status": "ok", "latency_ms": latency, "method": "api"}
        else:
            return {"status": "warn", "latency_ms": latency, "status_code": response.status_code, "method": "api"}
            
    except requests.exceptions.ConnectionError:
        return {"status": "disabled", "error": "endpoint not reachable", "latency_ms": None}
    except requests.exceptions.Timeout:
        return {"status": "fail", "error": "timeout", "latency_ms": round((time.time() - start) * 1000, 2)}
    except Exception as e:
        return {"status": "error", "error": str(e)}


def ping_fastapi(cfg: Dict, timeout: int = 2) -> Dict[str, Any]:
    """Проверяет доступность FastAPI сервера."""
    if not HAS_REQUESTS:
        return {"status": "error", "error": "requests library not available"}
    
    start = time.time()
    try:
        api_url = os.getenv("API_URL", "http://localhost:8000")
        health_url = f"{api_url.rstrip('/')}/health"
        
        response = requests.get(health_url, timeout=timeout)
        
        latency = round((time.time() - start) * 1000, 2)
        
        if response.status_code == 200:
            return {"status": "ok", "latency_ms": latency}
        else:
            return {"status": "warn", "latency_ms": latency, "status_code": response.status_code}
            
    except requests.exceptions.ConnectionError:
        return {"status": "disabled", "error": "API not running", "latency_ms": None}
    except requests.exceptions.Timeout:
        return {"status": "fail", "error": "timeout", "latency_ms": round((time.time() - start) * 1000, 2)}
    except Exception as e:
        return {"status": "error", "error": str(e)}


def ping_service(name: str, cfg: Dict, timeout: int = 2) -> Dict[str, Any]:
    """
    Проверяет доступность MCP-сервиса.
    
    Args:
        name: Имя сервиса
        cfg: Конфигурация сервиса из mcp.json
        timeout: Таймаут в секундах
        
    Returns:
        Словарь с результатами проверки
    """
    if not cfg.get("enabled", True):
        return {"status": "disabled", "latency_ms": None}
    
    # Определяем тип сервиса и вызываем соответствующую функцию
    name_lower = name.lower()
    
    if "supabase" in name_lower:
        # Supabase может быть настроен через URL или переменную окружения
        uri = cfg.get("url", "") or os.getenv("SUPABASE_URL", "")
        return ping_supabase(uri, timeout)
    elif "github" in name_lower or "gh" in name_lower:
        return ping_github(cfg, timeout)
    elif "docker" in name_lower:
        return ping_docker(cfg, timeout)
    elif "fastapi" in name_lower or "api" in name_lower or "reflexio-api" in name_lower:
        return ping_fastapi(cfg, timeout)
    elif "reflexio-edge" in name_lower or "edge" in name_lower:
        # Edge listener проверяется через его PID или порт (упрощённо)
        return {"status": "disabled", "latency_ms": None, "reason": "Edge listener check not implemented"}
    elif "brave" in name_lower:
        return ping_brave(cfg, timeout)
    elif "bright" in name_lower or "brightdata" in name_lower:
        return ping_brightdata(cfg, timeout)
    else:
        # Общая проверка для неизвестных сервисов
        return {"status": "unknown", "latency_ms": None, "reason": "service type not recognized"}


def validate_mcp_services() -> Dict[str, Any]:
    """
    Проверяет все MCP-сервисы из конфигурации.
    
    Returns:
        Словарь с результатами проверки всех сервисов
    """
    if not MCP_FILE.exists():
        return {
            "error": "MCP configuration file not found",
            "timestamp": datetime.utcnow().isoformat(),
        }
    
    try:
        with open(MCP_FILE, "r", encoding="utf-8") as f:
            mcp_data = json.load(f)
    except Exception as e:
        return {
            "error": f"Failed to load MCP config: {str(e)}",
            "timestamp": datetime.utcnow().isoformat(),
        }
    
    # Получаем список серверов
    servers = mcp_data.get("mcpServers", {})
    
    if not servers:
        return {
            "error": "No MCP servers configured",
            "timestamp": datetime.utcnow().isoformat(),
        }
    
    # Проверяем каждый сервис
    results = {}
    for name, config in servers.items():
        results[name] = ping_service(name, config)
    
    # Добавляем метаданные
    results["timestamp"] = datetime.now(timezone.utc).isoformat()
    results["total_services"] = len(servers)
    results["enabled_services"] = sum(
        1 for cfg in servers.values() if cfg.get("enabled", True)
    )
    results["healthy_services"] = sum(
        1 for r in results.values()
        if isinstance(r, dict) and r.get("status") == "ok"
    )
    
    return results


def main():
    """Точка входа для CLI."""
    import argparse
    
    parser = argparse.ArgumentParser(description="MCP Integration Validator")
    parser.add_argument(
        "--timeout",
        type=int,
        default=2,
        help="Таймаут проверки в секундах",
    )
    parser.add_argument(
        "--save",
        action="store_true",
        default=True,
        help="Сохранить результаты в mcp_health.json",
    )
    parser.add_argument(
        "--summary",
        action="store_true",
        help="Показать краткую сводку",
    )
    
    args = parser.parse_args()
    
    # Проверяем сервисы
    results = validate_mcp_services()
    
    if "error" in results:
        print(f"❌ {results['error']}", file=sys.stderr)
        return 1
    
    # Сохраняем результаты
    if args.save:
        METRICS_DIR.mkdir(parents=True, exist_ok=True)
        with open(REPORT_FILE, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
    
    # Выводим результаты
    if args.summary:
        print("=" * 70)
        print("MCP Services Health Summary")
        print("=" * 70)
        print(f"Total: {results.get('total_services', 0)}")
        print(f"Enabled: {results.get('enabled_services', 0)}")
        print(f"Healthy: {results.get('healthy_services', 0)}")
        print()
        print("Service Status:")
        print("-" * 70)
        
        for name, data in results.items():
            if name in ("timestamp", "total_services", "enabled_services", "healthy_services"):
                continue
            
            status = data.get("status", "unknown")
            latency = data.get("latency_ms")
            
            status_icon = "✅" if status == "ok" else "⚠️" if status == "warn" else "❌" if status == "fail" else "⚪"
            
            if latency is not None:
                print(f"{status_icon} {name:20s} {status:10s} {latency:8.2f} ms")
            else:
                reason = data.get("error") or data.get("reason", "")
                print(f"{status_icon} {name:20s} {status:10s} {reason}")
        
        print("=" * 70)
    else:
        # Полный вывод JSON
        print(json.dumps(results, indent=2, ensure_ascii=False))
    
    # Возвращаем код ошибки если есть проблемы
    if results.get("healthy_services", 0) < results.get("enabled_services", 0):
        return 1
    
    return 0


if __name__ == "__main__":
    sys.exit(main())

