"""
CEB-E Governance Loop

Применяет результаты аудита для автоматической настройки governance профиля.
"""

import json
import yaml
import argparse
from pathlib import Path
from datetime import datetime
import os


def apply_governance(results_path: Path = None, auto_upgrade: bool = True) -> dict:
    """Применяет governance профиль на основе результатов аудита."""
    if results_path is None:
        results_path = Path(".cursor/audit/audit_report.json")
    
    if not results_path.exists():
        print(f"⚠️  Файл аудита {results_path} не найден. Запустите аудит сначала.")
        return {"status": "error", "message": "audit report not found"}
    
    # Загружаем результаты аудита
    data = json.loads(results_path.read_text(encoding="utf-8"))
    
    score = data.get("score", 0)
    level = data.get("level", 0)
    reliability = data.get("ai_reliability_index", 0.0)
    
    # Определяем профиль на основе уровня зрелости и метрик
    # Safe-mode только если reliability очень низкая (< 0.5)
    if auto_upgrade and reliability < 0.5:
        profile = "safe-mode"
        description = "Безопасный режим: надёжность критически низкая, требуются меры"
    elif level >= 5:
        profile = "self-adaptive"
        description = "Полностью самоприспосабливающаяся система с автоматической оптимизацией"
    elif level >= 4:
        profile = "automated"
        description = "Автоматизированная система с метриками и управлением"
    elif level >= 3:
        profile = "pro"
        description = "Профессиональная система с определёнными процессами"
    elif level >= 2:
        profile = "foundational"
        description = "Базовая система с минимальным управлением"
    else:
        profile = "initial"
        description = "Начальный уровень — требуется настройка"
    
    # Создаём профиль governance
    governance_dir = Path(".cursor/governance")
    governance_dir.mkdir(parents=True, exist_ok=True)
    
    profile_path = governance_dir / "profile.yaml"
    
    # Загружаем текущий профиль для сохранения истории
    current_profile = None
    if profile_path.exists():
        try:
            current_data = yaml.safe_load(profile_path.read_text(encoding="utf-8"))
            current_profile = current_data.get("active_profile")
        except Exception:
            pass
    
    profile_data = {
        "current_level": level,
        "target_level": min(5, level + 1),
        "active_profile": profile,
        "previous_profile": current_profile,
        "description": description,
        "last_audit_score": score,
        "last_audit_level": level,
        "last_audit_date": data.get("date", ""),
        "reliability_index": reliability,
        "context_hit_rate": data.get("context_hit_rate", 0),
        "goals": {
            "enable_rules_engine": level >= 2,
            "enable_validation": level >= 3,
            "enable_mcp_gateway": level >= 3,
            "enable_governance_loop": level >= 3,
        },
        "governance_policies": [
            {
                "name": "Safety Mode",
                "condition": "reliability_index < 0.5",
                "action": "downgrade_to_safe_mode",
                "active": reliability < 0.5,
            },
            {
                "name": "Auto Upgrade",
                "condition": "audit_score >= 70",
                "action": "upgrade_to_automated",
                "active": score >= 70,
            },
            {
                "name": "Self-Adaptive",
                "condition": "audit_score >= 90 and reliability_index >= 0.95",
                "action": "enable_self_adaptive",
                "active": score >= 90 and reliability >= 0.95,
            },
            {
                "name": "MCP Service Failure",
                "condition": "mcp_governance.failed_services.length > 0",
                "action": "lower_mcp_priority",
                "description": "Понизить приоритет при сбоях MCP-сервисов",
                "active": False,  # Будет обновляться через validate-mcp playbook
            },
        ],
        "mcp_governance": {
            "last_check": None,
            "alerts": [],
            "failed_services": [],
            "warnings": [],
            "healthy_count": 0,
            "enabled_count": 0,
        },
        "osint_governance": {
            "avg_deepconf_confidence": None,
            "missions_completed": 0,
            "knowledge_health": "unknown",
            "auto_regeneration_active": False,
            "last_curation": None,
        },
        "config": {
            "auto_fix": level >= 3 and reliability >= 0.7,
            "strict_validation": level >= 4,
            "adaptive_rules": level >= 5,
            "metrics_collection": level >= 2,
            "auto_audit": level >= 4,
            "osint_auto_regeneration": level >= 5,
            "memory_auto_curation": level >= 5,
            "deepconf_feedback_loop": level >= 5,
            "methodology_compliance": level >= 5,
        },
        "methodology_compliance": {
            "active": False,
            "last_check": None,
            "compliance_score": None,
            "status": "unknown",
        },
        "metadata": {
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "version": "1.0",
        },
    }
    
    with profile_path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(profile_data, f, allow_unicode=True, default_flow_style=False)
    
    print(f"\n{'='*60}")
    print(f"Governance Loop Applied")
    print(f"{'='*60}")
    print(f"Профиль: {profile}")
    print(f"Описание: {description}")
    print(f"Уровень зрелости: {level}")
    print(f"Балл аудита: {score}")
    print(f"AI Reliability: {reliability:.2f}")
    print(f"Context Hit Rate: {data.get('context_hit_rate', 0):.2f}")
    
    if current_profile and current_profile != profile:
        print(f"🔄 Профиль изменён: {current_profile} → {profile}")
    elif not current_profile:
        print(f"✅ Профиль установлен: {profile}")
    
    print(f"\nКонфигурация сохранена: {profile_path}")
    print(f"{'='*60}\n")
    
    # Отправляем метрики в Supabase (если настроено)
    if os.getenv("DB_BACKEND") == "supabase":
        try:
            push_metrics_to_supabase(reliability, data.get("context_hit_rate", 0))
        except Exception as e:
            print(f"⚠️  Failed to push metrics to Supabase: {e}")
    
    return {
        "status": "success",
        "profile": profile,
        "profile_path": str(profile_path),
        "config": profile_data,
    }


def push_metrics_to_supabase(ai_reliability: float, context_hit_rate: float):
    """
    Отправляет метрики Governance в Supabase.
    
    Args:
        ai_reliability: AI Reliability Index
        context_hit_rate: Context Hit Rate
    """
    try:
        from src.storage.db import get_db
        
        db = get_db()
        
        metrics_to_push = {
            "ai_reliability": ai_reliability,
            "context_hit_rate": context_hit_rate,
        }
        
        for metric_name, value in metrics_to_push.items():
            # Проверяем существование метрики
            existing = db.select("metrics", filters={"metric_name": metric_name}, limit=1)
            
            metric_data = {
                "metric_name": metric_name,
                "metric_value": float(value),
                "updated_at": datetime.now().isoformat(),
            }
            
            if existing:
                # Обновляем существующую метрику
                db.update("metrics", existing[0]["id"], metric_data)
            else:
                # Создаём новую метрику
                db.insert("metrics", metric_data)
        
        print(f"✅ Metrics pushed to Supabase: {list(metrics_to_push.keys())}")
        
    except Exception as e:
        print(f"⚠️  Failed to push metrics: {e}")
        # Не критично, продолжаем работу


def insert_metric(metric_name: str, value: float):
    """
    Вставляет или обновляет метрику в Supabase.
    
    Args:
        metric_name: Имя метрики
        value: Значение метрики
    """
    try:
        from src.storage.db import get_db
        
        db = get_db()
        
        # Проверяем существование метрики
        existing = db.select("metrics", filters={"metric_name": metric_name}, limit=1)
        
        metric_data = {
            "metric_name": metric_name,
            "metric_value": float(value),
            "updated_at": datetime.now().isoformat(),
        }
        
        if existing:
            # Обновляем существующую метрику
            db.update("metrics", existing[0]["id"], metric_data)
        else:
            # Создаём новую метрику
            db.insert("metrics", metric_data)
        
    except Exception as e:
        print(f"⚠️  Failed to insert metric {metric_name}: {e}")


def main():
    parser = argparse.ArgumentParser(description="CEB-E Governance Loop")
    parser.add_argument(
        "--apply",
        choices=["results"],
        help="Применить governance на основе результатов аудита",
    )
    parser.add_argument(
        "--push-metrics",
        action="store_true",
        help="Отправить метрики в Supabase",
    )
    parser.add_argument(
        "--results",
        type=Path,
        default=Path(".cursor/audit/audit_report.json"),
        help="Путь к результатам аудита",
    )
    
    args = parser.parse_args()
    
    if args.push_metrics:
        # Загружаем метрики из аудита или cursor-metrics.json
        try:
            audit_path = Path(".cursor/audit/audit_report.json")
            if audit_path.exists():
                audit_data = json.loads(audit_path.read_text(encoding="utf-8"))
                reliability = audit_data.get("ai_reliability_index", 0.0)
                context_hit = audit_data.get("context_hit_rate", 0.0)
            else:
                # Пробуем из cursor-metrics.json
                metrics_path = Path("cursor-metrics.json")
                if metrics_path.exists():
                    metrics_data = json.loads(metrics_path.read_text(encoding="utf-8"))
                    gov_metrics = metrics_data.get("metrics", {}).get("governance", {})
                    reliability = gov_metrics.get("reliability_index", 0.0)
                    context_hit = gov_metrics.get("context_hit_rate", 0.0)
                else:
                    reliability = 0.0
                    context_hit = 0.0
            
            push_metrics_to_supabase(reliability, context_hit)
            print("✅ Metrics pushed to Supabase")
            return 0
        except Exception as e:
            print(f"❌ Failed to push metrics: {e}")
            return 1
    
    if args.apply == "results":
        result = apply_governance(args.results)
        return 0 if result["status"] == "success" else 1
    else:
        # По умолчанию применяем результаты
        result = apply_governance()
        return 0 if result["status"] == "success" else 1


if __name__ == "__main__":
    exit(main())

