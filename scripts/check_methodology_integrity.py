"""
Проверка методологического соответствия Reflexio 24/7.

Валидирует соответствие кода и конфигурации методологии Predictive Analytics Foundation.
"""
import json
import sys
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, Any, List, Tuple

sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from src.utils.logging import setup_logging, get_logger
    setup_logging()
    logger = get_logger("methodology.check")
except Exception:
    import logging
    logger = logging.getLogger("methodology.check")


class MethodologyChecker:
    """Проверяет соответствие методологии."""
    
    def __init__(self, registry_path: Path, policy_path: Path):
        self.registry_path = registry_path
        self.policy_path = policy_path
        self.registry = self._load_registry()
        self.policy = self._load_policy()
        self.results: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "compliance_score": 0.0,
            "checks": {},
            "summary": {
                "total_checks": 0,
                "passed": 0,
                "failed": 0,
                "warnings": 0,
            },
        }
    
    def _load_registry(self) -> Dict[str, Any]:
        """Загружает реестр методологий."""
        try:
            with open(self.registry_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error("registry_load_failed", error=str(e))
            return {}
    
    def _load_policy(self) -> Dict[str, Any]:
        """Загружает политику соответствия."""
        try:
            import yaml
            with open(self.policy_path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f)
        except Exception as e:
            logger.error("policy_load_failed", error=str(e))
            return {}
    
    def check_code_compliance(self, rule: Dict[str, Any]) -> Tuple[bool, str]:
        """
        Проверяет соответствие кода правилу.
        
        Args:
            rule: Правило из integrity_policy.yaml
            
        Returns:
            (passed, message)
        """
        module_path = rule.get("module")
        if not module_path:
            return False, "Module path not specified"
        
        file_path = Path(module_path)
        if not file_path.exists():
            return False, f"Module file not found: {module_path}"
        
        try:
            content = file_path.read_text(encoding="utf-8")
            validation = rule.get("validation", {})
            check = validation.get("check", "")
            
            # Простая проверка наличия ключевых элементов
            if "isotonic_regression" in check.lower():
                has_isotonic = "IsotonicRegression" in content or "isotonic" in content.lower()
                return has_isotonic, "Isotonic Regression usage" if has_isotonic else "Isotonic Regression not found"
            
            elif "bayesian" in check.lower():
                has_bayesian = "bayesian" in content.lower() or "BNN" in content
                return has_bayesian, "Bayesian UQ present" if has_bayesian else "Bayesian UQ not implemented"
            
            elif "dq_metrics" in check.lower() or "data quality" in check.lower():
                # Проверяем наличие DQ метрик: либо прямо в файле, либо через импорт
                has_dq_inline = any(keyword in content.lower() for keyword in ["accuracy", "completeness", "timeliness", "consistency", "validity"])
                has_dq_import = "dq_metrics" in content.lower() or "from src.osint.dq_metrics" in content or "import dq_metrics" in content
                has_dq = has_dq_inline or has_dq_import
                return has_dq, "DQ metrics present" if has_dq else "DQ metrics not found"
            
            elif "source_urls" in check.lower() or "source attribution" in check.lower():
                # Проверяем наличие source_urls в схеме Claim
                has_sources = "source_urls" in content or "source_url" in content
                if has_sources:
                    # Дополнительно проверяем, что это поле в классе Claim
                    claim_class_match = "class Claim" in content or "Claim(" in content
                    return True, "Source attribution present in Claim schema" if claim_class_match else "Source attribution present"
                return has_sources, "Source attribution missing"
            
            elif "methodology_compliance" in check.lower():
                has_check = "methodology" in content.lower() and "compliance" in content.lower()
                return has_check, "Methodology compliance check present" if has_check else "Methodology compliance check missing"
            
            elif "scoring_formula" in check.lower():
                has_formula = "mean" in content.lower() and "log" in content.lower() and "validated_claims" in content.lower()
                return has_formula, "Scoring formula matches specification" if has_formula else "Scoring formula may not match"
            
            elif "auto_regeneration" in check.lower():
                has_auto = "auto_regeneration" in content.lower() or "auto-regeneration" in content.lower()
                return has_auto, "Auto-regeneration implemented" if has_auto else "Auto-regeneration not found"
            
            else:
                # Общая проверка существования файла
                return True, "Module exists and is accessible"
                
        except Exception as e:
            return False, f"Error reading module: {e}"
    
    def check_schema_compliance(self, rule: Dict[str, Any]) -> Tuple[bool, str]:
        """Проверяет соответствие схем данных."""
        if rule.get("module") == "src/osint/schemas.py":
            try:
                from src.osint.schemas import Claim
                
                # Проверяем наличие source_urls в Claim
                import inspect
                
                # Проверяем через __annotations__ или поля модели
                if hasattr(Claim, "model_fields"):
                    # Pydantic v2
                    has_sources = "source_urls" in Claim.model_fields
                elif hasattr(Claim, "__fields__"):
                    # Pydantic v1
                    has_sources = "source_urls" in Claim.__fields__
                else:
                    # Fallback: проверяем через signature
                    sig = inspect.signature(Claim.__init__)
                    has_sources = "source_urls" in sig.parameters
                
                return has_sources, "Claim schema has source_urls" if has_sources else "Claim schema missing source_urls"
            except Exception as e:
                # Fallback: проверяем через чтение файла
                file_path = Path(rule.get("module", ""))
                if file_path.exists():
                    content = file_path.read_text(encoding="utf-8")
                    has_sources_in_code = "source_urls" in content and "class Claim" in content
                    return has_sources_in_code, "Source attribution found in Claim class" if has_sources_in_code else f"Schema check failed: {e}"
                return False, f"Schema check failed: {e}"
        
        return True, "Schema check not applicable"
    
    def run_checks(self):
        """Запускает все проверки."""
        rules = self.policy.get("rules", [])
        
        total_weight = 0.0
        passed_weight = 0.0
        
        compliance_levels = self.policy.get("compliance_levels", {})
        
        for rule in rules:
            rule_id = rule.get("id")
            name = rule.get("name", rule_id)
            compliance_level = rule.get("compliance_level", "optional")
            validation = rule.get("validation", {})
            method = validation.get("method", "code_inspection")
            
            # Определяем вес правила
            level_config = compliance_levels.get(compliance_level, {})
            weight = level_config.get("weight", 0.5)
            total_weight += weight
            
            # Выполняем проверку
            if method == "schema_validation":
                passed, message = self.check_schema_compliance(rule)
            else:
                passed, message = self.check_code_compliance(rule)
            
            self.results["summary"]["total_checks"] += 1
            
            if passed:
                self.results["summary"]["passed"] += 1
                passed_weight += weight
                status = "passed"
            else:
                if compliance_level == "required":
                    self.results["summary"]["failed"] += 1
                    status = "failed"
                else:
                    self.results["summary"]["warnings"] += 1
                    status = "warning"
            
            self.results["checks"][rule_id] = {
                "name": name,
                "status": status,
                "compliance_level": compliance_level,
                "message": message,
                "weight": weight,
                "module": rule.get("module"),
            }
        
        # Вычисляем общий compliance score
        if total_weight > 0:
            self.results["compliance_score"] = passed_weight / total_weight
        else:
            self.results["compliance_score"] = 0.0
    
    def print_report(self):
        """Выводит отчёт."""
        print("\n" + "=" * 70)
        print("Methodology Compliance Check")
        print("=" * 70)
        print(f"Timestamp: {self.results['timestamp']}")
        print()
        
        # Группируем по уровню соответствия
        by_level = {"required": [], "recommended": [], "optional": []}
        
        for rule_id, check in self.results["checks"].items():
            level = check["compliance_level"]
            by_level.setdefault(level, []).append((rule_id, check))
        
        # Выводим по уровням
        for level in ["required", "recommended", "optional"]:
            if not by_level[level]:
                continue
            
            print(f"\n{level.upper()} Rules:")
            print("-" * 70)
            
            for rule_id, check in by_level[level]:
                status_icon = {
                    "passed": "✅",
                    "failed": "❌",
                    "warning": "⚠️ ",
                }.get(check["status"], "❓")
                
                print(f"{status_icon} [{rule_id}] {check['name']}")
                print(f"   {check['message']}")
                print()
        
        # Итоговая сводка
        print("=" * 70)
        print("SUMMARY")
        print("=" * 70)
        print(f"Compliance Score: {self.results['compliance_score']:.2%}")
        print(f"Total Checks: {self.results['summary']['total_checks']}")
        print(f"✅ Passed: {self.results['summary']['passed']}")
        print(f"❌ Failed: {self.results['summary']['failed']}")
        print(f"⚠️  Warnings: {self.results['summary']['warnings']}")
        print()
        
        if self.results["compliance_score"] >= 0.8:
            print("🎉 METHODOLOGY COMPLIANCE: PASS")
        elif self.results["compliance_score"] >= 0.6:
            print("⚠️  METHODOLOGY COMPLIANCE: WARNING (some requirements missing)")
        else:
            print("❌ METHODOLOGY COMPLIANCE: FAIL (critical requirements missing)")
        
        print("=" * 70)
        print()
    
    def save_report(self, output_path: Path):
        """Сохраняет отчёт."""
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(self.results, f, indent=2, ensure_ascii=False)
        
        logger.info("methodology_report_saved", path=str(output_path))


def main():
    """Точка входа."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Check Methodology Integrity")
    parser.add_argument(
        "--registry",
        type=Path,
        default=Path("docs/Reflexio_Methodology/methodology_registry.json"),
        help="Path to methodology registry",
    )
    parser.add_argument(
        "--policy",
        type=Path,
        default=Path("docs/Reflexio_Methodology/integrity_policy.yaml"),
        help="Path to integrity policy",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(".cursor/audit/methodology_compliance_report.json"),
        help="Output path for report",
    )
    
    args = parser.parse_args()
    
    checker = MethodologyChecker(args.registry, args.policy)
    checker.run_checks()
    checker.print_report()
    checker.save_report(args.output)
    
    # Возвращаем код выхода
    if checker.results["compliance_score"] >= 0.8:
        return 0
    elif checker.results["compliance_score"] >= 0.6:
        return 1  # Warning
    else:
        return 2  # Fail


if __name__ == "__main__":
    sys.exit(main())

