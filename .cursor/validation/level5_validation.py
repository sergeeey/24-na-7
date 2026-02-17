"""
Комплексная проверка компонентов Level 5 — Self-Adaptive.

Проверяет все ключевые элементы и их интеграцию.
"""
import json
import sys
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, Any, List, Tuple

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

try:
    from src.utils.logging import setup_logging, get_logger
    setup_logging()
    logger = get_logger("validation.level5")
except Exception:
    import logging
    logger = logging.getLogger("validation.level5")


class Level5Validator:
    """Валидатор компонентов Level 5."""
    
    def __init__(self):
        self.results: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "checks": {},
            "summary": {
                "total_checks": 0,
                "passed": 0,
                "failed": 0,
                "warnings": 0,
            },
        }
    
    def check(self, name: str, condition: bool, message: str = "", details: Dict[str, Any] = None):
        """Выполняет проверку и записывает результат."""
        self.results["summary"]["total_checks"] += 1
        
        if condition:
            self.results["summary"]["passed"] += 1
            status = "✅ PASSED"
        else:
            self.results["summary"]["failed"] += 1
            status = "❌ FAILED"
        
        self.results["checks"][name] = {
            "status": "passed" if condition else "failed",
            "message": message,
            "details": details or {},
        }
        
        print(f"{status}: {name}")
        if message:
            print(f"   {message}")
        if details:
            for key, value in details.items():
                print(f"   {key}: {value}")
        print()
    
    def warn(self, name: str, message: str = "", details: Dict[str, Any] = None):
        """Добавляет предупреждение."""
        self.results["summary"]["warnings"] += 1
        
        self.results["checks"][name] = {
            "status": "warning",
            "message": message,
            "details": details or {},
        }
        
        print(f"⚠️  WARNING: {name}")
        if message:
            print(f"   {message}")
        print()
    
    def check_deepconf_feedback(self) -> bool:
        """Проверка 1: DeepConf Feedback Loop."""
        print("=" * 70)
        print("Проверка 1: DeepConf Feedback Loop")
        print("=" * 70)
        
        all_passed = True
        
        # A. Проверка метрики
        metrics_file = Path("cursor-metrics.json")
        if not metrics_file.exists():
            self.check(
                "deepconf_metrics_file_exists",
                False,
                "cursor-metrics.json не найден",
            )
            all_passed = False
        else:
            self.check(
                "deepconf_metrics_file_exists",
                True,
                "cursor-metrics.json найден",
            )
            
            try:
                data = json.loads(metrics_file.read_text(encoding="utf-8"))
                osint_metrics = data.get("metrics", {}).get("osint", {})
                
                avg_confidence = osint_metrics.get("avg_deepconf_confidence")
                
                if avg_confidence is None:
                    self.warn(
                        "deepconf_confidence_present",
                        "avg_deepconf_confidence отсутствует (может быть None при отсутствии миссий)",
                        {"value": None},
                    )
                else:
                    is_valid = 0.0 <= avg_confidence <= 1.0
                    self.check(
                        "deepconf_confidence_valid",
                        is_valid,
                        f"avg_deepconf_confidence = {avg_confidence:.2f}",
                        {"value": avg_confidence, "range": "0.0-1.0"},
                    )
                    if not is_valid:
                        all_passed = False
                    
                    # Проверка триггеров
                    if avg_confidence < 0.8:
                        self.warn(
                            "deepconf_low_confidence",
                            f"Confidence ниже порога ({avg_confidence:.2f} < 0.8). Должна быть активирована регенерация.",
                            {"threshold": 0.8, "current": avg_confidence},
                        )
                    elif avg_confidence >= 0.95:
                        self.check(
                            "deepconf_high_confidence",
                            True,
                            f"Confidence высокий ({avg_confidence:.2f} >= 0.95). Должна быть приоритизация обновления.",
                            {"threshold": 0.95, "current": avg_confidence},
                        )
                
            except Exception as e:
                self.check(
                    "deepconf_metrics_parse",
                    False,
                    f"Ошибка парсинга: {e}",
                )
                all_passed = False
        
        # B. Проверка скрипта
        feedback_script = Path("src/osint/deepconf_feedback.py")
        if feedback_script.exists():
            self.check("deepconf_feedback_script_exists", True)
        else:
            self.check("deepconf_feedback_script_exists", False)
            all_passed = False
        
        return all_passed
    
    def check_adaptive_scoring(self) -> bool:
        """Проверка 2: Adaptive Mission Scoring."""
        print("=" * 70)
        print("Проверка 2: Adaptive Mission Scoring")
        print("=" * 70)
        
        all_passed = True
        
        # A. Проверка скрипта
        scoring_script = Path("src/osint/adaptive_scoring.py")
        if not scoring_script.exists():
            self.check("adaptive_scoring_script_exists", False)
            all_passed = False
        else:
            self.check("adaptive_scoring_script_exists", True)
            
            # Проверка результатов миссий
            results_dir = Path(".cursor/osint/results")
            if results_dir.exists():
                result_files = list(results_dir.glob("*_result_*.json"))
                
                if len(result_files) == 0:
                    self.warn(
                        "osint_results_exist",
                        "Нет результатов миссий для анализа. Запустите хотя бы одну миссию.",
                        {"results_count": 0},
                    )
                else:
                    self.check(
                        "osint_results_exist",
                        True,
                        f"Найдено результатов: {len(result_files)}",
                        {"results_count": len(result_files)},
                    )
            else:
                self.warn(
                    "results_dir_exists",
                    "Директория результатов не существует. Создана автоматически.",
                )
                results_dir.mkdir(parents=True, exist_ok=True)
        
        # B. Проверка формулы
        try:
            from src.osint.adaptive_scoring import calculate_mission_score
            from src.osint.schemas import MissionResult, Claim
            
            # Тестовый результат
            test_result = MissionResult(
                mission_id="test",
                completed_at=datetime.now(timezone.utc).isoformat(),
                tasks_completed=1,
                total_claims=5,
                validated_claims=4,
                avg_confidence=0.85,
            )
            
            score = calculate_mission_score(test_result)
            is_valid_score = 0 <= score <= 10
            
            self.check(
                "adaptive_scoring_formula",
                is_valid_score,
                f"Формула работает, score = {score:.2f}",
                {"test_score": score, "test_confidence": 0.85, "test_validated": 4},
            )
            if not is_valid_score:
                all_passed = False
                
        except Exception as e:
            self.check("adaptive_scoring_import", False, f"Ошибка импорта: {e}")
            all_passed = False
        
        return all_passed
    
    def check_memory_curator(self) -> bool:
        """Проверка 3: Memory Curation Agent."""
        print("=" * 70)
        print("Проверка 3: Memory Curation Agent")
        print("=" * 70)
        
        all_passed = True
        
        # A. Проверка скрипта
        curator_script = Path("src/osint/memory_curator.py")
        if not curator_script.exists():
            self.check("memory_curator_script_exists", False)
            all_passed = False
        else:
            self.check("memory_curator_script_exists", True)
            
            # Проверка Memory Bank
            memory_file = Path(".cursor/memory/osint_research.md")
            if memory_file.exists():
                content = memory_file.read_text(encoding="utf-8")
                claims_count = content.count("## ")
                
                self.check(
                    "memory_bank_exists",
                    True,
                    f"Memory Bank найден, утверждений: {claims_count}",
                )
                
                # Проверка на опровергнутые
                refuted_count = content.count("❌")
                if refuted_count > 0:
                    self.warn(
                        "refuted_claims_found",
                        f"Найдено {refuted_count} опровергнутых утверждений. Запустите curator с --remove-refuted.",
                        {"refuted_count": refuted_count},
                    )
            else:
                self.warn(
                    "memory_bank_exists",
                    "Memory Bank не найден. Будет создан при первой миссии.",
                )
        
        return all_passed
    
    def check_governance_integration(self) -> bool:
        """Проверка 4: Интеграция с Governance Loop."""
        print("=" * 70)
        print("Проверка 4: Governance Loop Integration")
        print("=" * 70)
        
        all_passed = True
        
        # A. Проверка profile.yaml
        profile_file = Path(".cursor/governance/profile.yaml")
        if not profile_file.exists():
            self.check("governance_profile_exists", False)
            all_passed = False
        else:
            self.check("governance_profile_exists", True)
            
            try:
                import yaml
                with open(profile_file, "r", encoding="utf-8") as f:
                    profile = yaml.safe_load(f)
                
                # Проверка osint_governance
                osint_gov = profile.get("osint_governance")
                if osint_gov:
                    self.check(
                        "osint_governance_section",
                        True,
                        "Секция osint_governance присутствует",
                    )
                else:
                    self.warn(
                        "osint_governance_section",
                        "Секция osint_governance отсутствует. Запустите level5-upgrade.",
                    )
                
                # Проверка уровня
                current_level = profile.get("current_level", 0)
                self.check(
                    "governance_level",
                    current_level >= 4,
                    f"Текущий уровень: {current_level}",
                    {"target_level": 5, "current_level": current_level},
                )
                if current_level < 4:
                    all_passed = False
                
            except Exception as e:
                self.check("governance_profile_parse", False, f"Ошибка парсинга: {e}")
                all_passed = False
        
        # B. Проверка governance_loop.py
        loop_script = Path(".cursor/metrics/governance_loop.py")
        if loop_script.exists():
            content = loop_script.read_text(encoding="utf-8")
            has_osint = "osint_governance" in content
            
            self.check(
                "governance_loop_osint_integration",
                has_osint,
                "governance_loop.py содержит osint_governance",
            )
            if not has_osint:
                all_passed = False
        else:
            self.check("governance_loop_script_exists", False)
            all_passed = False
        
        return all_passed
    
    def check_mcp_intelligence(self) -> bool:
        """Проверка 5: MCP Intelligence Pack."""
        print("=" * 70)
        print("Проверка 5: MCP Intelligence Pack (Brave + Bright Data)")
        print("=" * 70)
        
        all_passed = True
        
        # A. Проверка конфигурации
        mcp_file = Path(".cursor/mcp.json")
        if not mcp_file.exists():
            self.check("mcp_config_exists", False)
            all_passed = False
        else:
            try:
                data = json.loads(mcp_file.read_text(encoding="utf-8"))
                mcp_servers = data.get("mcpServers", {})
                
                brave_config = mcp_servers.get("brave")
                brightdata_config = mcp_servers.get("brightdata")
                
                if brave_config:
                    brave_enabled = brave_config.get("enabled", False)
                    self.check(
                        "brave_configured",
                        True,
                        f"Brave Search настроен, enabled: {brave_enabled}",
                    )
                    if not brave_enabled:
                        all_passed = False
                else:
                    self.check("brave_configured", False)
                    all_passed = False
                
                if brightdata_config:
                    bright_enabled = brightdata_config.get("enabled", False)
                    self.check(
                        "brightdata_configured",
                        True,
                        f"Bright Data настроен, enabled: {bright_enabled}",
                    )
                    if not bright_enabled:
                        all_passed = False
                else:
                    self.check("brightdata_configured", False)
                    all_passed = False
                
            except Exception as e:
                self.check("mcp_config_parse", False, f"Ошибка парсинга: {e}")
                all_passed = False
        
        # B. Проверка API ключей
        env_file = Path(".env")
        if env_file.exists():
            env_content = env_file.read_text(encoding="utf-8")
            has_brave_key = "BRAVE_API_KEY" in env_content
            has_bright_key = "BRIGHTDATA_API_KEY" in env_content
            
            self.check(
                "brave_api_key_set",
                has_brave_key,
                "BRAVE_API_KEY присутствует в .env",
            )
            if not has_brave_key:
                self.warn(
                    "brave_api_key_missing",
                    "Добавьте BRAVE_API_KEY в .env для использования Brave Search",
                )
            
            self.check(
                "brightdata_api_key_set",
                has_bright_key,
                "BRIGHTDATA_API_KEY присутствует в .env",
            )
            if not has_bright_key:
                self.warn(
                    "brightdata_api_key_missing",
                    "Добавьте BRIGHTDATA_API_KEY в .env для использования Bright Data",
                )
        else:
            self.warn("env_file_exists", ".env файл не найден")
        
        # C. Проверка клиентов
        try:
            from src.mcp.clients import get_brave_client, get_bright_client
            self.check("mcp_clients_importable", True)
        except Exception as e:
            self.check("mcp_clients_importable", False, f"Ошибка импорта: {e}")
            all_passed = False
        
        return all_passed
    
    def check_playbooks_hooks(self) -> bool:
        """Проверка 6: Playbooks Suite и Hooks System."""
        print("=" * 70)
        print("Проверка 6: Playbooks Suite и Hooks System")
        print("=" * 70)
        
        all_passed = True
        
        # A. Проверка playbooks
        playbooks_dir = Path(".cursor/playbooks")
        required_playbooks = [
            "osint-mission.yaml",
            "level5-upgrade.yaml",
            "validate-mcp.yaml",
        ]
        
        for playbook_name in required_playbooks:
            playbook_path = playbooks_dir / playbook_name
            exists = playbook_path.exists()
            self.check(
                f"playbook_{playbook_name.replace('.yaml', '')}_exists",
                exists,
                f"Playbook: {playbook_name}",
            )
            if not exists:
                all_passed = False
        
        # B. Проверка hooks
        hooks_file = Path(".cursor/hooks/on_event.py")
        if hooks_file.exists():
            content = hooks_file.read_text(encoding="utf-8")
            has_new_topic = "new_topic_detected" in content
            has_intelligence = "intelligence" in content or "combined_search_and_scrape" in content
            
            self.check(
                "hooks_new_topic_handler",
                has_new_topic,
                "Hook для new_topic_detected присутствует",
            )
            if not has_new_topic:
                all_passed = False
            
            self.check(
                "hooks_intelligence_integration",
                has_intelligence,
                "Hook интегрирован с intelligence",
            )
            if not has_intelligence:
                all_passed = False
        else:
            self.check("hooks_file_exists", False)
            all_passed = False
        
        return all_passed
    
    def run_all_checks(self):
        """Запускает все проверки."""
        print("\n" + "=" * 70)
        print("Reflexio 24/7 — Level 5 Validation")
        print("=" * 70)
        print(f"Timestamp: {self.results['timestamp']}")
        print()
        
        checks = [
            ("DeepConf Feedback Loop", self.check_deepconf_feedback),
            ("Adaptive Mission Scoring", self.check_adaptive_scoring),
            ("Memory Curation Agent", self.check_memory_curator),
            ("Governance Integration", self.check_governance_integration),
            ("MCP Intelligence Pack", self.check_mcp_intelligence),
            ("Playbooks & Hooks", self.check_playbooks_hooks),
        ]
        
        for name, check_func in checks:
            try:
                check_func()
            except Exception as e:
                self.check(
                    f"{name.lower().replace(' ', '_')}_error",
                    False,
                    f"Ошибка при проверке: {e}",
                )
                logger.exception(f"Error in {name} check")
        
        # Финальная сводка
        self.print_summary()
        
        # Сохранение отчёта
        self.save_report()
    
    def print_summary(self):
        """Выводит итоговую сводку."""
        print("=" * 70)
        print("ИТОГОВАЯ СВОДКА")
        print("=" * 70)
        
        summary = self.results["summary"]
        
        print(f"Всего проверок: {summary['total_checks']}")
        print(f"✅ Пройдено: {summary['passed']}")
        print(f"❌ Провалено: {summary['failed']}")
        print(f"⚠️  Предупреждений: {summary['warnings']}")
        print()
        
        if summary['failed'] == 0:
            print("🎉 ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ!")
            if summary['warnings'] > 0:
                print("⚠️  Есть предупреждения — проверьте их выше.")
        else:
            print("❌ ЕСТЬ ПРОВАЛЕННЫЕ ПРОВЕРКИ!")
            print("Исправьте ошибки перед использованием Level 5.")
        
        print("=" * 70)
        print()
    
    def save_report(self):
        """Сохраняет отчёт."""
        report_file = Path(".cursor/validation/level5_validation_report.json")
        report_file.parent.mkdir(parents=True, exist_ok=True)
        
        with open(report_file, "w", encoding="utf-8") as f:
            json.dump(self.results, f, indent=2, ensure_ascii=False)
        
        print(f"📄 Отчёт сохранён: {report_file}")


def main():
    """Точка входа."""
    validator = Level5Validator()
    validator.run_all_checks()
    
    # Возвращаем код выхода
    if validator.results["summary"]["failed"] == 0:
        return 0
    else:
        return 1


if __name__ == "__main__":
    sys.exit(main())

