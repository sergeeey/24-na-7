"""
Диагностика Bright Data Proxy.

Проверяет доступность, скорость, геолокацию и работоспособность proxy.
"""
import json
import sys
import time
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, Any, Optional

sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from src.utils.logging import setup_logging, get_logger
    setup_logging()
    logger = get_logger("proxy.diagnostics")
except Exception:
    import logging
    logger = logging.getLogger("proxy.diagnostics")


class ProxyDiagnostics:
    """Диагностика Bright Data Proxy."""
    
    def __init__(self, proxy_http: Optional[str] = None, proxy_ws: Optional[str] = None):
        import os
        
        self.proxy_http = proxy_http or os.getenv("BRIGHTDATA_PROXY_HTTP")
        self.proxy_ws = proxy_ws or os.getenv("BRIGHTDATA_PROXY_WS")
        
        if not self.proxy_http:
            raise ValueError("BRIGHTDATA_PROXY_HTTP not set")
    
    def check_connectivity(self, timeout: int = 10) -> Dict[str, Any]:
        """
        Проверяет доступность proxy.
        
        Args:
            timeout: Таймаут в секундах
            
        Returns:
            Результат проверки с latency
        """
        try:
            import requests
            
            test_url = "https://api.ipify.org?format=json"
            
            # Настройка proxy
            proxies = {
                "http": self.proxy_http,
                "https": self.proxy_http,
            }
            
            start = time.time()
            response = requests.get(test_url, proxies=proxies, timeout=timeout)
            latency_ms = (time.time() - start) * 1000
            
            if response.status_code == 200:
                data = response.json()
                ip = data.get("ip", "unknown")
                
                return {
                    "status": "ok",
                    "latency_ms": round(latency_ms, 2),
                    "ip": ip,
                    "status_code": response.status_code,
                }
            else:
                return {
                    "status": "error",
                    "latency_ms": round(latency_ms, 2),
                    "status_code": response.status_code,
                    "error": f"HTTP {response.status_code}",
                }
                
        except requests.exceptions.Timeout:
            return {
                "status": "timeout",
                "latency_ms": timeout * 1000,
                "error": "Connection timeout",
            }
        except requests.exceptions.ProxyError as e:
            return {
                "status": "proxy_error",
                "error": str(e),
            }
        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
            }
    
    def check_geolocation(self, timeout: int = 10) -> Dict[str, Any]:
        """
        Проверяет геолокацию proxy IP.
        
        Args:
            timeout: Таймаут в секундах
            
        Returns:
            Информация о геолокации
        """
        try:
            import requests
            
            # Сначала получаем IP через proxy
            ip_response = requests.get(
                "https://api.ipify.org?format=json",
                proxies={"http": self.proxy_http, "https": self.proxy_http},
                timeout=timeout,
            )
            
            if ip_response.status_code != 200:
                return {"status": "error", "error": "Could not get IP address"}
            
            ip = ip_response.json().get("ip")
            
            # Получаем геолокацию (без proxy, это публичный API)
            geo_response = requests.get(
                f"https://ipapi.co/{ip}/json/",
                timeout=timeout,
            )
            
            if geo_response.status_code == 200:
                geo_data = geo_response.json()
                return {
                    "status": "ok",
                    "ip": ip,
                    "country": geo_data.get("country_name"),
                    "country_code": geo_data.get("country_code"),
                    "city": geo_data.get("city"),
                    "region": geo_data.get("region"),
                    "timezone": geo_data.get("timezone"),
                    "isp": geo_data.get("org"),
                }
            else:
                return {
                    "status": "error",
                    "ip": ip,
                    "error": "Could not get geolocation",
                }
                
        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
            }
    
    def check_speed(self, test_url: str = "https://www.example.com", timeout: int = 15) -> Dict[str, Any]:
        """
        Проверяет скорость загрузки через proxy.
        
        Args:
            test_url: URL для тестирования
            timeout: Таймаут в секундах
            
        Returns:
            Метрики скорости
        """
        try:
            import requests
            
            proxies = {
                "http": self.proxy_http,
                "https": self.proxy_http,
            }
            
            start = time.time()
            response = requests.get(test_url, proxies=proxies, timeout=timeout, stream=True)
            connect_time = time.time() - start
            
            # Читаем первые байты для измерения скорости
            first_byte_time = time.time()
            content_length = 0
            chunk_start = time.time()
            
            for chunk in response.iter_content(chunk_size=8192):
                if content_length == 0:
                    first_byte_time = time.time() - chunk_start
                content_length += len(chunk)
                if content_length > 100000:  # Ограничиваем до 100KB для теста
                    break
            
            total_time = time.time() - start
            download_speed = (content_length / 1024) / total_time if total_time > 0 else 0  # KB/s
            
            return {
                "status": "ok",
                "connect_time_ms": round(connect_time * 1000, 2),
                "first_byte_time_ms": round(first_byte_time * 1000, 2),
                "total_time_ms": round(total_time * 1000, 2),
                "download_speed_kbps": round(download_speed, 2),
                "bytes_downloaded": content_length,
            }
            
        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
            }
    
    def check_js_rendering(self, test_url: str = "https://httpbin.org/html", timeout: int = 20) -> Dict[str, Any]:
        """
        Проверяет способность proxy обрабатывать JavaScript страницы.
        
        Args:
            test_url: URL для тестирования
            timeout: Таймаут в секундах
            
        Returns:
            Результат проверки JS рендеринга
        """
        try:
            import requests
            
            proxies = {
                "http": self.proxy_http,
                "https": self.proxy_http,
            }
            
            start = time.time()
            response = requests.get(test_url, proxies=proxies, timeout=timeout)
            latency_ms = (time.time() - start) * 1000
            
            if response.status_code == 200:
                content = response.text
                has_js = "<script" in content.lower() or "javascript" in content.lower()
                
                return {
                    "status": "ok",
                    "latency_ms": round(latency_ms, 2),
                    "js_detected": has_js,
                    "content_length": len(content),
                    "status_code": response.status_code,
                }
            else:
                return {
                    "status": "error",
                    "latency_ms": round(latency_ms, 2),
                    "status_code": response.status_code,
                    "error": f"HTTP {response.status_code}",
                }
                
        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
            }
    
    def run_full_diagnostics(self) -> Dict[str, Any]:
        """
        Запускает полную диагностику proxy.
        
        Returns:
            Полный отчёт диагностики
        """
        results = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "proxy_http": self.proxy_http[:50] + "..." if len(self.proxy_http) > 50 else self.proxy_http,
            "proxy_ws": self.proxy_ws[:50] + "..." if self.proxy_ws and len(self.proxy_ws) > 50 else self.proxy_ws,
            "checks": {},
            "summary": {
                "overall_status": "unknown",
                "checks_passed": 0,
                "checks_failed": 0,
            },
        }
        
        logger.info("proxy_diagnostics_started")
        
        # 1. Проверка подключения
        print("\n[1/4] Checking connectivity...")
        connectivity = self.check_connectivity()
        results["checks"]["connectivity"] = connectivity
        
        if connectivity.get("status") == "ok":
            results["summary"]["checks_passed"] += 1
            print(f"✅ Connectivity: OK (latency: {connectivity.get('latency_ms', 0):.2f}ms, IP: {connectivity.get('ip', 'unknown')})")
        else:
            results["summary"]["checks_failed"] += 1
            print(f"❌ Connectivity: FAILED ({connectivity.get('error', 'unknown error')})")
        
        # 2. Проверка геолокации
        print("\n[2/4] Checking geolocation...")
        geolocation = self.check_geolocation()
        results["checks"]["geolocation"] = geolocation
        
        if geolocation.get("status") == "ok":
            results["summary"]["checks_passed"] += 1
            print(f"✅ Geolocation: {geolocation.get('country', 'unknown')}, {geolocation.get('city', 'unknown')}")
        else:
            results["summary"]["checks_failed"] += 1
            print(f"⚠️  Geolocation: Could not determine ({geolocation.get('error', 'unknown')})")
        
        # 3. Проверка скорости
        print("\n[3/4] Checking speed...")
        speed = self.check_speed()
        results["checks"]["speed"] = speed
        
        if speed.get("status") == "ok":
            results["summary"]["checks_passed"] += 1
            print(f"✅ Speed: {speed.get('download_speed_kbps', 0):.2f} KB/s")
            print(f"   Connect: {speed.get('connect_time_ms', 0):.2f}ms, First byte: {speed.get('first_byte_time_ms', 0):.2f}ms")
        else:
            results["summary"]["checks_failed"] += 1
            print(f"❌ Speed: FAILED ({speed.get('error', 'unknown')})")
        
        # 4. Проверка JS рендеринга
        print("\n[4/4] Checking JS rendering...")
        js_rendering = self.check_js_rendering()
        results["checks"]["js_rendering"] = js_rendering
        
        if js_rendering.get("status") == "ok":
            results["summary"]["checks_passed"] += 1
            print(f"✅ JS Rendering: OK (latency: {js_rendering.get('latency_ms', 0):.2f}ms)")
        else:
            results["summary"]["checks_failed"] += 1
            print(f"❌ JS Rendering: FAILED ({js_rendering.get('error', 'unknown')})")
        
        # Итоговый статус
        total_checks = len(results["checks"])
        passed = results["summary"]["checks_passed"]
        
        if passed == total_checks:
            results["summary"]["overall_status"] = "healthy"
        elif passed >= total_checks * 0.5:
            results["summary"]["overall_status"] = "degraded"
        else:
            results["summary"]["overall_status"] = "unhealthy"
        
        logger.info("proxy_diagnostics_completed", status=results["summary"]["overall_status"], passed=passed, total=total_checks)
        
        return results
    
    def generate_markdown_report(self, results: Dict[str, Any], output_path: Path) -> None:
        """
        Генерирует Markdown отчёт диагностики.
        
        Args:
            results: Результаты диагностики
            output_path: Путь для сохранения отчёта
        """
        lines = [
            "# Bright Data Proxy Diagnostics Report",
            "",
            f"**Timestamp:** {results['timestamp']}",
            f"**Overall Status:** {results['summary']['overall_status'].upper()}",
            "",
            "---",
            "",
            "## Summary",
            "",
            f"- **Checks Passed:** {results['summary']['checks_passed']} / {len(results['checks'])}",
            f"- **Checks Failed:** {results['summary']['checks_failed']} / {len(results['checks'])}",
            "",
            "---",
            "",
            "## Detailed Results",
            "",
        ]
        
        # Connectivity
        conn = results["checks"].get("connectivity", {})
        lines.append("### 1. Connectivity")
        lines.append("")
        if conn.get("status") == "ok":
            lines.append(f"✅ **Status:** OK")
            lines.append(f"- **Latency:** {conn.get('latency_ms', 0):.2f} ms")
            lines.append(f"- **IP Address:** {conn.get('ip', 'unknown')}")
        else:
            lines.append(f"❌ **Status:** FAILED")
            lines.append(f"- **Error:** {conn.get('error', 'unknown')}")
        lines.append("")
        
        # Geolocation
        geo = results["checks"].get("geolocation", {})
        lines.append("### 2. Geolocation")
        lines.append("")
        if geo.get("status") == "ok":
            lines.append(f"✅ **Status:** OK")
            lines.append(f"- **Country:** {geo.get('country', 'unknown')} ({geo.get('country_code', 'unknown')})")
            lines.append(f"- **City:** {geo.get('city', 'unknown')}")
            lines.append(f"- **Region:** {geo.get('region', 'unknown')}")
            lines.append(f"- **Timezone:** {geo.get('timezone', 'unknown')}")
            lines.append(f"- **ISP:** {geo.get('isp', 'unknown')}")
        else:
            lines.append(f"⚠️  **Status:** Could not determine")
            lines.append(f"- **Error:** {geo.get('error', 'unknown')}")
        lines.append("")
        
        # Speed
        speed = results["checks"].get("speed", {})
        lines.append("### 3. Speed")
        lines.append("")
        if speed.get("status") == "ok":
            lines.append(f"✅ **Status:** OK")
            lines.append(f"- **Download Speed:** {speed.get('download_speed_kbps', 0):.2f} KB/s")
            lines.append(f"- **Connect Time:** {speed.get('connect_time_ms', 0):.2f} ms")
            lines.append(f"- **First Byte Time:** {speed.get('first_byte_time_ms', 0):.2f} ms")
            lines.append(f"- **Total Time:** {speed.get('total_time_ms', 0):.2f} ms")
        else:
            lines.append(f"❌ **Status:** FAILED")
            lines.append(f"- **Error:** {speed.get('error', 'unknown')}")
        lines.append("")
        
        # JS Rendering
        js = results["checks"].get("js_rendering", {})
        lines.append("### 4. JavaScript Rendering")
        lines.append("")
        if js.get("status") == "ok":
            lines.append(f"✅ **Status:** OK")
            lines.append(f"- **Latency:** {js.get('latency_ms', 0):.2f} ms")
            lines.append(f"- **Content Length:** {js.get('content_length', 0)} bytes")
        else:
            lines.append(f"❌ **Status:** FAILED")
            lines.append(f"- **Error:** {js.get('error', 'unknown')}")
        lines.append("")
        
        # Рекомендации
        lines.extend([
            "---",
            "",
            "## Recommendations",
            "",
        ])
        
        if results["summary"]["overall_status"] == "healthy":
            lines.append("✅ Proxy is working correctly. No action needed.")
        elif results["summary"]["overall_status"] == "degraded":
            lines.append("⚠️  Some checks failed. Review the errors above.")
        else:
            lines.append("❌ Proxy is not working properly. Check credentials and network connectivity.")
        
        lines.append("")
        
        # Сохраняем
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text("\n".join(lines), encoding="utf-8")
        
        logger.info("proxy_diagnostics_report_generated", path=str(output_path))


def main():
    """CLI для диагностики proxy."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Bright Data Proxy Diagnostics")
    parser.add_argument(
        "--proxy-http",
        help="HTTP proxy URL (или из .env)",
    )
    parser.add_argument(
        "--proxy-ws",
        help="WebSocket proxy URL (или из .env)",
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        default=Path(".cursor/audit/proxy_diagnostics.json"),
        help="JSON output path",
    )
    parser.add_argument(
        "--output-markdown",
        type=Path,
        default=Path(".cursor/audit/proxy_diagnostics.md"),
        help="Markdown output path",
    )
    
    args = parser.parse_args()
    
    try:
        diagnostics = ProxyDiagnostics(proxy_http=args.proxy_http, proxy_ws=args.proxy_ws)
        
        print("\n" + "=" * 70)
        print("Bright Data Proxy Diagnostics")
        print("=" * 70)
        
        results = diagnostics.run_full_diagnostics()
        
        # Сохраняем JSON
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        with open(args.output_json, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        
        # Генерируем Markdown
        diagnostics.generate_markdown_report(results, args.output_markdown)
        
        print("\n" + "=" * 70)
        print("SUMMARY")
        print("=" * 70)
        print(f"Overall Status: {results['summary']['overall_status'].upper()}")
        print(f"Checks Passed: {results['summary']['checks_passed']} / {len(results['checks'])}")
        print(f"\nReports saved:")
        print(f"  - JSON: {args.output_json}")
        print(f"  - Markdown: {args.output_markdown}")
        print("=" * 70)
        print()
        
        return 0 if results["summary"]["overall_status"] == "healthy" else 1
        
    except ValueError as e:
        print(f"❌ Error: {e}")
        print("\nMake sure BRIGHTDATA_PROXY_HTTP is set in .env or passed as --proxy-http")
        return 1
    except Exception as e:
        logger.exception("proxy_diagnostics_failed")
        print(f"❌ Unexpected error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())













