#!/usr/bin/env python3
"""
SAFE CLI — запуск SAFE проверок.
"""
import sys
import argparse
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, Any

# Добавляем путь к проекту
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from .cursor.validation.safe.checks import SAFEChecker


def run_safe_checks(mode: str = "audit") -> Dict[str, Any]:
    """
    Запускает SAFE проверки.
    
    Args:
        mode: "strict" (fail on errors) или "audit" (только отчёт)
        
    Returns:
        Результаты проверок
    """
    checker = SAFEChecker()
    results = {
        "timestamp": datetime.utcnow().isoformat(),
        "mode": mode,
        "checks": [],
        "summary": {
            "total": 0,
            "passed": 0,
            "failed": 0,
            "warnings": 0,
        }
    }
    
    # Проверка 1: PII в примере текста
    test_text = "Contact me at john.doe@example.com or +7 (999) 123-45-67"
    has_pii, detected, masked = checker.check_pii_in_text(test_text)
    results["checks"].append({
        "name": "PII Detection",
        "status": "passed" if has_pii else "warning",
        "message": f"Detected: {detected}" if has_pii else "No PII patterns configured",
        "detected": detected,
        "masked": masked[:100] if masked else None,
    })
    if has_pii:
        results["summary"]["passed"] += 1
    else:
        results["summary"]["warnings"] += 1
    results["summary"]["total"] += 1
    
    # Проверка 2: Секреты в логах
    test_log = "API call with api_key=sk-1234567890abcdef failed"
    has_secrets, secret_types = checker.check_secrets_in_logs(test_log)
    results["checks"].append({
        "name": "Secrets in Logs",
        "status": "passed" if has_secrets else "warning",
        "message": f"Detected secrets: {secret_types}" if has_secrets else "No secrets detected (test)",
        "detected": secret_types,
    })
    if has_secrets:
        results["summary"]["passed"] += 1
    else:
        results["summary"]["warnings"] += 1
    results["summary"]["total"] += 1
    
    # Проверка 3: Домен allowlist
    test_urls = [
        "https://api.search.brave.com/search",
        "https://evil.com/steal",
        "https://lkmyliwjleegjkcgespp.supabase.co/rest/v1/",
    ]
    for url in test_urls:
        allowed, reason = checker.check_domain_access(url)
        results["checks"].append({
            "name": f"Domain Access: {url.split('/')[2]}",
            "status": "passed" if allowed else "failed",
            "message": reason,
        })
        if allowed:
            results["summary"]["passed"] += 1
        else:
            results["summary"]["failed"] += 1
        results["summary"]["total"] += 1
    
    # Проверка 4: Размер файла (тест на несуществующем файле)
    test_file = Path("/tmp/test_file.txt")
    if test_file.exists():
        valid, reason = checker.check_file_size(test_file)
        results["checks"].append({
            "name": "File Size Check",
            "status": "passed" if valid else "failed",
            "message": reason,
        })
        if valid:
            results["summary"]["passed"] += 1
        else:
            results["summary"]["failed"] += 1
        results["summary"]["total"] += 1
    
    # Проверка 5: Payload валидация
    test_payload = {
        "text": "Email: test@example.com",
        "data": "Some data",
    }
    payload_result = checker.validate_payload(test_payload, require_pii_mask=True)
    results["checks"].append({
        "name": "Payload Validation",
        "status": "passed" if payload_result["valid"] else "failed",
        "message": f"Valid: {payload_result['valid']}, Warnings: {len(payload_result.get('warnings', []))}",
        "warnings": payload_result.get("warnings", []),
    })
    if payload_result["valid"]:
        results["summary"]["passed"] += 1
    else:
        results["summary"]["failed"] += 1
    results["summary"]["total"] += 1
    
    return results


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="SAFE Security Validation")
    parser.add_argument(
        "--mode",
        choices=["strict", "audit"],
        default="audit",
        help="Validation mode: strict (fail on errors) or audit (report only)"
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Output JSON file path"
    )
    parser.add_argument(
        "--summary",
        action="store_true",
        help="Print summary table"
    )
    
    args = parser.parse_args()
    
    # Запускаем проверки
    results = run_safe_checks(mode=args.mode)
    
    # Выводим результаты
    if args.summary:
        print("=" * 70)
        print("SAFE Security Validation Summary")
        print("=" * 70)
        print(f"Mode: {results['mode']}")
        print(f"Total Checks: {results['summary']['total']}")
        print(f"✅ Passed: {results['summary']['passed']}")
        print(f"❌ Failed: {results['summary']['failed']}")
        print(f"⚠️  Warnings: {results['summary']['warnings']}")
        print()
        print("Checks:")
        for check in results["checks"]:
            status_icon = "✅" if check["status"] == "passed" else "❌" if check["status"] == "failed" else "⚠️"
            print(f"  {status_icon} {check['name']}: {check['message']}")
        print("=" * 70)
    else:
        print(json.dumps(results, indent=2))
    
    # Сохраняем в файл
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        print(f"\nReport saved to: {args.output}")
    
    # Возвращаем код выхода
    if args.mode == "strict" and results["summary"]["failed"] > 0:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()











