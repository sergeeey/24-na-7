"""
Автоматический сбор метрик из тестов и обновление чеклиста.
Reflexio v2.1 — Surpass Smart Noter Sprint

Собирает метрики из:
- pytest JSON отчётов
- Логов тестов
- Прямых измерений (WER, Latency, etc.)
"""
import json
import yaml
import re
from pathlib import Path
from typing import Dict, Any, Optional, List
import sys

def load_checklist(checklist_path: Path) -> Dict[str, Any]:
    """Загружает чеклист."""
    with open(checklist_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def save_checklist(checklist: Dict[str, Any], checklist_path: Path):
    """Сохраняет чеклист."""
    with open(checklist_path, "w", encoding="utf-8") as f:
        yaml.dump(checklist, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

def parse_pytest_json_report(report_path: Path) -> Dict[str, Any]:
    """Парсит pytest JSON отчёт."""
    if not report_path.exists():
        return {}
    
    with open(report_path, "r", encoding="utf-8") as f:
        return json.load(f)

def extract_wer_from_tests(report: Dict[str, Any]) -> Optional[str]:
    """Извлекает WER из тестов ASR accuracy."""
    # Ищем в summary или в логах тестов
    tests = report.get("tests", [])
    for test in tests:
        if "asr_accuracy" in test.get("nodeid", "").lower():
            # Пытаемся найти WER в выводе
            call = test.get("call", {})
            stdout = call.get("stdout", "")
            
            # Ищем паттерн "WER: X.X%"
            match = re.search(r'WER[:\s]+([\d.]+)%?', stdout, re.IGNORECASE)
            if match:
                return f"{match.group(1)}%"
    
    return None

def extract_latency_from_tests(report: Dict[str, Any]) -> Optional[str]:
    """Извлекает Latency из тестов ASR latency."""
    tests = report.get("tests", [])
    for test in tests:
        if "asr_latency" in test.get("nodeid", "").lower():
            call = test.get("call", {})
            stdout = call.get("stdout", "")
            
            # Ищем паттерн "Latency: X.X сек" или "X.Xs"
            match = re.search(r'Latency[:\s]+([\d.]+)\s*(сек|s|sec)', stdout, re.IGNORECASE)
            if match:
                return f"{match.group(1)} сек"
            
            # Альтернативный паттерн: просто число с "s"
            match = re.search(r'([\d.]+)\s*(сек|s|sec)', stdout)
            if match:
                return f"{match.group(1)} сек"
    
    return None

def extract_coverage_from_report(report: Dict[str, Any]) -> Optional[str]:
    """Извлекает coverage из отчёта."""
    summary = report.get("summary", {})
    total = summary.get("total", 0)
    passed = summary.get("passed", 0)
    
    if total > 0:
        coverage_pct = (passed / total) * 100
        return f"{coverage_pct:.1f}%"
    
    return None

def extract_offline_duration_from_tests(report: Dict[str, Any]) -> Optional[str]:
    """Извлекает длительность офлайн транскрипции."""
    tests = report.get("tests", [])
    for test in tests:
        if "asr_offline" in test.get("nodeid", "").lower():
            call = test.get("call", {})
            stdout = call.get("stdout", "")
            
            # Ищем паттерн "≥ 30 мин" или "X мин"
            match = re.search(r'([\d.]+)\s*(мин|min)', stdout, re.IGNORECASE)
            if match:
                minutes = float(match.group(1))
                return f"≥ {int(minutes)} мин"
    
    return None

def extract_deepconf_from_tests(report: Dict[str, Any]) -> Optional[str]:
    """Извлекает DeepConf score из тестов."""
    tests = report.get("tests", [])
    for test in tests:
        if "deepconf" in test.get("nodeid", "").lower() or "critic" in test.get("nodeid", "").lower():
            call = test.get("call", {})
            stdout = call.get("stdout", "")
            
            # Ищем паттерн "DeepConf: 0.XX" или "confidence: 0.XX"
            match = re.search(r'(?:DeepConf|confidence)[:\s]+([\d.]+)', stdout, re.IGNORECASE)
            if match:
                score = float(match.group(1))
                return f"{score:.2f}"
    
    return None

def extract_factual_consistency_from_tests(report: Dict[str, Any]) -> Optional[str]:
    """Извлекает Factual consistency из тестов."""
    tests = report.get("tests", [])
    for test in tests:
        if "factual" in test.get("nodeid", "").lower() or "consistency" in test.get("nodeid", "").lower():
            call = test.get("call", {})
            stdout = call.get("stdout", "")
            
            # Ищем паттерн "Factual consistency: XX%"
            match = re.search(r'Factual[:\s]+([\d.]+)%?', stdout, re.IGNORECASE)
            if match:
                return f"{match.group(1)}%"
    
    return None

def extract_token_entropy_from_tests(report: Dict[str, Any]) -> Optional[str]:
    """Извлекает Token entropy из тестов."""
    tests = report.get("tests", [])
    for test in tests:
        if "entropy" in test.get("nodeid", "").lower():
            call = test.get("call", {})
            stdout = call.get("stdout", "")
            
            # Ищем паттерн "Token entropy: 0.XX"
            match = re.search(r'Token[:\s]+entropy[:\s]+([\d.]+)', stdout, re.IGNORECASE)
            if match:
                return match.group(1)
    
    return None

def update_metric_in_checklist(
    checklist: Dict[str, Any],
    epic_key: str,
    metric_name: str,
    value: Any,
) -> bool:
    """Обновляет метрику в чеклисте."""
    epic = checklist.get("epics", {}).get(epic_key)
    if not epic:
        return False
    
    metrics = epic.get("metrics", [])
    for metric in metrics:
        if metric.get("name") == metric_name:
            metric["current"] = value
            return True
    
    return False

def auto_update_metrics_from_report(
    checklist_path: Path,
    report_path: Path,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """
    Автоматически обновляет метрики в чеклисте из pytest отчёта.
    
    Returns:
        {
            "updated": List[str],  # Список обновлённых метрик
            "skipped": List[str],  # Метрики, которые не удалось найти
        }
    """
    checklist = load_checklist(checklist_path)
    report = parse_pytest_json_report(report_path)
    
    updated = []
    skipped = []
    
    # Маппинг метрик на функции извлечения
    metric_extractors = {
        ("epic_i_asr", "WER"): extract_wer_from_tests,
        ("epic_i_asr", "Latency"): extract_latency_from_tests,
        ("epic_i_asr", "Офлайн транскрипция"): extract_offline_duration_from_tests,
        ("epic_ii_llm", "Factual consistency"): extract_factual_consistency_from_tests,
        ("epic_ii_llm", "DeepConf score"): extract_deepconf_from_tests,
        ("epic_ii_llm", "Token entropy"): extract_token_entropy_from_tests,
    }
    
    # Обновляем метрики
    for (epic_key, metric_name), extractor in metric_extractors.items():
        value = extractor(report)
        if value:
            if not dry_run:
                update_metric_in_checklist(checklist, epic_key, metric_name, value)
            updated.append(f"{epic_key}:{metric_name} = {value}")
        else:
            skipped.append(f"{epic_key}:{metric_name}")
    
    # Сохраняем чеклист
    if not dry_run and updated:
        save_checklist(checklist, checklist_path)
    
    return {
        "updated": updated,
        "skipped": skipped,
    }

def main():
    """Основная функция."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Auto-update metrics from test reports")
    parser.add_argument(
        "--checklist",
        default=".cursor/tasks/surpass_smart_noter_checklist.yaml",
        help="Path to checklist YAML file",
    )
    parser.add_argument(
        "--report",
        default="tests/.report.json",
        help="Path to pytest JSON report",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Don't update checklist, just show what would be updated",
    )
    
    args = parser.parse_args()
    
    checklist_path = Path(args.checklist)
    report_path = Path(args.report)
    
    if not checklist_path.exists():
        print(f"❌ Checklist not found: {checklist_path}")
        sys.exit(1)
    
    if not report_path.exists():
        print(f"⚠️  Report not found: {report_path}")
        print("   Run tests with: pytest --json-report --json-report-file=tests/.report.json")
        sys.exit(0)
    
    result = auto_update_metrics_from_report(
        checklist_path,
        report_path,
        dry_run=args.dry_run,
    )
    
    if args.dry_run:
        print("🔍 Dry-run mode — no changes made")
        print()
    
    if result["updated"]:
        print("✅ Обновлённые метрики:")
        for item in result["updated"]:
            print(f"  - {item}")
    else:
        print("⚠️  Не найдено метрик для обновления")
    
    if result["skipped"]:
        print(f"\n⏭️  Пропущено (не найдено в отчёте): {len(result['skipped'])}")
        if len(result["skipped"]) <= 5:
            for item in result["skipped"]:
                print(f"  - {item}")
    
    if not args.dry_run and result["updated"]:
        print(f"\n💾 Чеклист обновлён: {checklist_path}")

if __name__ == "__main__":
    main()





