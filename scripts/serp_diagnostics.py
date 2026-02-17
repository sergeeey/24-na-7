"""
SERP Diagnostics — диагностика поисковых систем и зон Bright Data.

Проверяет доступность Google, Bing, Yahoo через разные зоны,
измеряет задержки и создаёт рейтинг качества поиска.
"""
import json
import sys
import time
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from src.utils.logging import setup_logging, get_logger
    setup_logging()
    logger = get_logger("serp.diagnostics")
except Exception:
    import logging
    logger = logging.getLogger("serp.diagnostics")


class SERPDiagnostics:
    """Диагностика SERP API для разных поисковых систем и зон."""
    
    def __init__(self):
        """Инициализация диагностики."""
        import os
        self.api_key = os.getenv("BRIGHTDATA_API_KEY")
        
        if not self.api_key:
            raise ValueError("BRIGHTDATA_API_KEY not set in environment")
        
        # Загружаем конфигурацию зон
        self.zones_config_path = Path(".cursor/config/brightdata_zones.json")
        self.zones_config = self._load_zones_config()
        
        # Тестовые запросы для проверки
        self.test_queries = [
            "artificial intelligence",
            "latest technology news",
            "climate change",
        ]
    
    def _load_zones_config(self) -> Dict[str, Any]:
        """Загружает конфигурацию зон."""
        if not self.zones_config_path.exists():
            logger.warning("zones_config_not_found", path=str(self.zones_config_path))
            return {"zones": {}}
        
        try:
            with open(self.zones_config_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error("zones_config_load_failed", error=str(e))
            return {"zones": {}}
    
    def test_serp_engine(
        self,
        search_engine: str,
        zone: str,
        query: str,
        timeout: int = 30,
    ) -> Dict[str, Any]:
        """
        Тестирует поисковую систему через указанную зону.
        
        Args:
            search_engine: Поисковая система ("google", "bing", "yahoo")
            zone: Зона Bright Data
            query: Тестовый запрос
            timeout: Таймаут в секундах
            
        Returns:
            Результаты теста
        """
        try:
            from src.mcp.clients import get_bright_client
            
            bright = get_bright_client(zone=zone)
            
            start_time = time.time()
            
            # Запрос через SERP API
            serp_data = bright.scrape_serp(
                query=query,
                search_engine=search_engine,
                zone=zone,
                format="raw",
            )
            
            latency_ms = (time.time() - start_time) * 1000
            
            if not serp_data:
                return {
                    "status": "error",
                    "latency_ms": round(latency_ms, 2),
                    "error": "No data returned",
                }
            
            # Извлекаем результаты
            results = bright.extract_serp_results(serp_data)
            
            return {
                "status": "ok",
                "latency_ms": round(latency_ms, 2),
                "results_count": len(results),
                "zone": zone,
                "search_engine": search_engine,
                "query": query,
            }
            
        except Exception as e:
            return {
                "status": "error",
                "latency_ms": None,
                "error": str(e),
                "zone": zone,
                "search_engine": search_engine,
                "query": query,
            }
    
    def test_zone(
        self,
        zone_name: str,
        zone_config: Dict[str, Any],
        search_engines: List[str] = None,
    ) -> Dict[str, Any]:
        """
        Тестирует зону на разных поисковых системах.
        
        Args:
            zone_name: Имя зоны
            zone_config: Конфигурация зоны
            search_engines: Список поисковых систем для теста
            
        Returns:
            Результаты тестирования зоны
        """
        if search_engines is None:
            # Определяем поисковые системы из конфигурации зоны
            engines = zone_config.get("engines", [])
            if engines:
                search_engines = engines
            else:
                # По умолчанию тестируем Google и Bing
                search_engines = ["google", "bing"]
        
        zone_results = {
            "zone": zone_name,
            "config": zone_config,
            "tests": {},
            "summary": {
                "total_tests": 0,
                "passed": 0,
                "failed": 0,
                "avg_latency_ms": 0.0,
                "total_results": 0,
            },
        }
        
        # Тестируем каждую поисковую систему
        for engine in search_engines:
            engine_results = []
            
            # Используем первый тестовый запрос
            test_query = self.test_queries[0]
            
            logger.info("serp_zone_test_started", zone=zone_name, engine=engine)
            
            result = self.test_serp_engine(
                search_engine=engine,
                zone=zone_name,
                query=test_query,
            )
            
            engine_results.append(result)
            
            # Обновляем статистику
            if result.get("status") == "ok":
                zone_results["summary"]["passed"] += 1
                zone_results["summary"]["total_results"] += result.get("results_count", 0)
                latency = result.get("latency_ms", 0)
                if latency:
                    zone_results["summary"]["avg_latency_ms"] += latency
            else:
                zone_results["summary"]["failed"] += 1
            
            zone_results["summary"]["total_tests"] += 1
            zone_results["tests"][engine] = engine_results
        
        # Вычисляем среднюю задержку
        if zone_results["summary"]["passed"] > 0:
            zone_results["summary"]["avg_latency_ms"] = round(
                zone_results["summary"]["avg_latency_ms"] / zone_results["summary"]["passed"],
                2
            )
        
        # Вычисляем успешность
        if zone_results["summary"]["total_tests"] > 0:
            success_rate = (zone_results["summary"]["passed"] / zone_results["summary"]["total_tests"]) * 100
            zone_results["summary"]["success_rate"] = round(success_rate, 2)
        else:
            zone_results["summary"]["success_rate"] = 0.0
        
        return zone_results
    
    def run_full_diagnostics(self) -> Dict[str, Any]:
        """
        Запускает полную диагностику всех зон и поисковых систем.
        
        Returns:
            Полный отчёт диагностики
        """
        results = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "zones": {},
            "summary": {
                "total_zones": 0,
                "zones_tested": 0,
                "zones_healthy": 0,
                "zones_degraded": 0,
                "zones_unhealthy": 0,
            },
            "rankings": {
                "by_latency": [],
                "by_success_rate": [],
                "by_results_count": [],
            },
        }
        
        zones = self.zones_config.get("zones", {})
        
        if not zones:
            logger.warning("no_zones_configured")
            results["error"] = "No zones configured"
            return results
        
        results["summary"]["total_zones"] = len(zones)
        
        logger.info("serp_diagnostics_started", zones_count=len(zones))
        
        # Тестируем каждую зону
        for zone_name, zone_config in zones.items():
            zone_type = zone_config.get("type", "unknown")
            
            # Тестируем только SERP зоны
            if zone_type != "serp":
                logger.debug("zone_skipped_not_serp", zone=zone_name, type=zone_type)
                continue
            
            print(f"\n[Testing Zone] {zone_name} ({zone_config.get('name', zone_name)})")
            
            zone_results = self.test_zone(zone_name, zone_config)
            results["zones"][zone_name] = zone_results
            
            results["summary"]["zones_tested"] += 1
            
            # Классифицируем состояние зоны
            success_rate = zone_results["summary"]["success_rate"]
            if success_rate >= 90:
                results["summary"]["zones_healthy"] += 1
                status = "healthy"
            elif success_rate >= 50:
                results["summary"]["zones_degraded"] += 1
                status = "degraded"
            else:
                results["summary"]["zones_unhealthy"] += 1
                status = "unhealthy"
            
            zone_results["status"] = status
            
            print(f"  Status: {status.upper()}")
            print(f"  Success Rate: {success_rate}%")
            print(f"  Avg Latency: {zone_results['summary']['avg_latency_ms']}ms")
            print(f"  Results: {zone_results['summary']['total_results']}")
        
        # Создаём рейтинги
        results["rankings"] = self._create_rankings(results["zones"])
        
        logger.info("serp_diagnostics_completed", zones_tested=results["summary"]["zones_tested"])
        
        return results
    
    def _create_rankings(self, zones: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
        """
        Создаёт рейтинги зон по разным метрикам.
        
        Args:
            zones: Результаты тестирования зон
            
        Returns:
            Рейтинги по латентности, успешности и количеству результатов
        """
        rankings = {
            "by_latency": [],
            "by_success_rate": [],
            "by_results_count": [],
        }
        
        for zone_name, zone_data in zones.items():
            summary = zone_data.get("summary", {})
            
            # Рейтинг по латентности (меньше = лучше)
            if summary.get("avg_latency_ms"):
                rankings["by_latency"].append({
                    "zone": zone_name,
                    "latency_ms": summary["avg_latency_ms"],
                    "success_rate": summary.get("success_rate", 0),
                })
            
            # Рейтинг по успешности (больше = лучше)
            rankings["by_success_rate"].append({
                "zone": zone_name,
                "success_rate": summary.get("success_rate", 0),
                "latency_ms": summary.get("avg_latency_ms", 0),
            })
            
            # Рейтинг по количеству результатов (больше = лучше)
            rankings["by_results_count"].append({
                "zone": zone_name,
                "results_count": summary.get("total_results", 0),
                "success_rate": summary.get("success_rate", 0),
            })
        
        # Сортируем рейтинги
        rankings["by_latency"].sort(key=lambda x: x["latency_ms"])
        rankings["by_success_rate"].sort(key=lambda x: x["success_rate"], reverse=True)
        rankings["by_results_count"].sort(key=lambda x: x["results_count"], reverse=True)
        
        return rankings
    
    def generate_markdown_report(
        self,
        results: Dict[str, Any],
        output_path: Path,
    ) -> None:
        """
        Генерирует Markdown отчёт диагностики.
        
        Args:
            results: Результаты диагностики
            output_path: Путь для сохранения отчёта
        """
        lines = [
            "# SERP Diagnostics Report",
            "",
            f"**Timestamp:** {results['timestamp']}",
            "",
            "---",
            "",
            "## Summary",
            "",
            f"- **Total Zones:** {results['summary']['total_zones']}",
            f"- **Zones Tested:** {results['summary']['zones_tested']}",
            f"- **Healthy Zones:** {results['summary']['zones_healthy']}",
            f"- **Degraded Zones:** {results['summary']['zones_degraded']}",
            f"- **Unhealthy Zones:** {results['summary']['zones_unhealthy']}",
            "",
            "---",
            "",
            "## Zone Rankings",
            "",
        ]
        
        # Рейтинг по латентности
        lines.append("### 🚀 Fastest Zones (by Latency)")
        lines.append("")
        lines.append("| Rank | Zone | Latency (ms) | Success Rate |")
        lines.append("|------|------|--------------|--------------|")
        
        for idx, ranking in enumerate(results["rankings"]["by_latency"][:5], 1):
            lines.append(
                f"| {idx} | `{ranking['zone']}` | {ranking['latency_ms']}ms | {ranking['success_rate']}% |"
            )
        lines.append("")
        
        # Рейтинг по успешности
        lines.append("### ✅ Most Reliable Zones (by Success Rate)")
        lines.append("")
        lines.append("| Rank | Zone | Success Rate | Latency (ms) |")
        lines.append("|------|------|--------------|--------------|")
        
        for idx, ranking in enumerate(results["rankings"]["by_success_rate"][:5], 1):
            lines.append(
                f"| {idx} | `{ranking['zone']}` | {ranking['success_rate']}% | {ranking['latency_ms']}ms |"
            )
        lines.append("")
        
        # Рейтинг по количеству результатов
        lines.append("### 📊 Most Productive Zones (by Results Count)")
        lines.append("")
        lines.append("| Rank | Zone | Results Count | Success Rate |")
        lines.append("|------|------|--------------|--------------|")
        
        for idx, ranking in enumerate(results["rankings"]["by_results_count"][:5], 1):
            lines.append(
                f"| {idx} | `{ranking['zone']}` | {ranking['results_count']} | {ranking['success_rate']}% |"
            )
        lines.append("")
        
        # Детальная информация по зонам
        lines.extend([
            "---",
            "",
            "## Detailed Zone Results",
            "",
        ])
        
        for zone_name, zone_data in results["zones"].items():
            summary = zone_data["summary"]
            status = zone_data.get("status", "unknown")
            
            status_emoji = {
                "healthy": "✅",
                "degraded": "⚠️",
                "unhealthy": "❌",
            }.get(status, "❓")
            
            lines.append(f"### {status_emoji} {zone_name}")
            lines.append("")
            lines.append(f"- **Status:** {status.upper()}")
            lines.append(f"- **Success Rate:** {summary['success_rate']}%")
            lines.append(f"- **Avg Latency:** {summary['avg_latency_ms']}ms")
            lines.append(f"- **Total Results:** {summary['total_results']}")
            lines.append(f"- **Tests Passed:** {summary['passed']}/{summary['total_tests']}")
            lines.append("")
            
            # Детали по поисковым системам
            lines.append("**Engine Tests:**")
            lines.append("")
            for engine, engine_tests in zone_data.get("tests", {}).items():
                for test in engine_tests:
                    if test.get("status") == "ok":
                        lines.append(
                            f"- ✅ **{engine}**: {test.get('results_count', 0)} results, "
                            f"{test.get('latency_ms', 0)}ms"
                        )
                    else:
                        lines.append(
                            f"- ❌ **{engine}**: {test.get('error', 'Unknown error')}"
                        )
            lines.append("")
        
        # Рекомендации
        lines.extend([
            "---",
            "",
            "## Recommendations",
            "",
        ])
        
        if results["summary"]["zones_healthy"] > 0:
            best_zone = results["rankings"]["by_latency"][0] if results["rankings"]["by_latency"] else None
            if best_zone:
                lines.append(f"✅ **Recommended Zone:** `{best_zone['zone']}` (lowest latency)")
                lines.append("")
        
        if results["summary"]["zones_unhealthy"] > 0:
            lines.append("⚠️  **Action Required:** Some zones are unhealthy. Review errors above.")
            lines.append("")
        
        lines.append("**Next Steps:**")
        lines.append("1. Use the recommended zone for critical missions")
        lines.append("2. Monitor zone health regularly")
        lines.append("3. Update zone configuration if needed")
        lines.append("")
        
        # Сохраняем
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text("\n".join(lines), encoding="utf-8")
        
        logger.info("serp_diagnostics_report_generated", path=str(output_path))


def main():
    """CLI для диагностики SERP."""
    import argparse
    
    parser = argparse.ArgumentParser(description="SERP Diagnostics")
    parser.add_argument(
        "--output-json",
        type=Path,
        default=Path(".cursor/audit/serp_diagnostics.json"),
        help="JSON output path",
    )
    parser.add_argument(
        "--output-markdown",
        type=Path,
        default=Path(".cursor/audit/serp_diagnostics.md"),
        help="Markdown output path",
    )
    
    args = parser.parse_args()
    
    try:
        diagnostics = SERPDiagnostics()
        
        print("\n" + "=" * 70)
        print("SERP Diagnostics")
        print("=" * 70)
        print()
        
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
        print(f"Zones Tested: {results['summary']['zones_tested']}")
        print(f"Healthy: {results['summary']['zones_healthy']}")
        print(f"Degraded: {results['summary']['zones_degraded']}")
        print(f"Unhealthy: {results['summary']['zones_unhealthy']}")
        
        if results["rankings"]["by_latency"]:
            best = results["rankings"]["by_latency"][0]
            print(f"\n🏆 Best Zone: {best['zone']} ({best['latency_ms']}ms)")
        
        print(f"\nReports saved:")
        print(f"  - JSON: {args.output_json}")
        print(f"  - Markdown: {args.output_markdown}")
        print("=" * 70)
        print()
        
        return 0 if results["summary"]["zones_unhealthy"] == 0 else 1
        
    except ValueError as e:
        print(f"❌ Error: {e}")
        print("\nMake sure BRIGHTDATA_API_KEY is set in .env")
        return 1
    except Exception as e:
        logger.exception("serp_diagnostics_failed")
        print(f"❌ Unexpected error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())













