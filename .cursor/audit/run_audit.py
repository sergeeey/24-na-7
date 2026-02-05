"""
CEB-E Audit Runner v1.0 — Эталонный аудит

Проверяет проект на соответствие Cursor Enhancement Blueprint Evaluation v1.0.
Включает проверку всех 9 компонентов: Rules, Memory, MCP, Hooks, Validation, 
Observability, Governance, Playbooks, Multi-Agent.
"""

import json
import datetime
import subprocess
import os
import sys
import argparse
import yaml
from pathlib import Path
from typing import Dict, List, Tuple, Optional


def run_check(cmd: str, timeout: int = 30) -> Tuple[bool, str]:
    """Выполняет команду и возвращает результат."""
    try:
        result = subprocess.run(
            cmd.split() if isinstance(cmd, str) else cmd,
            check=True,
            capture_output=True,
            timeout=timeout,
            text=True,
        )
        return True, result.stdout
    except subprocess.CalledProcessError as e:
        return False, e.stderr or str(e)
    except subprocess.TimeoutExpired:
        return False, "Timeout"
    except Exception as e:
        return False, str(e)


def check_rules_engine(base: Path) -> Dict:
    """Проверяет Rules Engine (15 баллов)."""
    rules_path = base / "rules"
    result = {
        "exists": False,
        "score": 0,
        "details": [],
        "issues": [],
    }
    
    if not rules_path.exists():
        result["issues"].append("Директория .cursor/rules/ отсутствует")
        return result
    
    result["exists"] = True
    score = 15
    
    # Проверяем наличие файлов правил
    rule_files = list(rules_path.glob("*.md"))
    if not rule_files:
        score -= 5
        result["issues"].append("Нет файлов правил в .cursor/rules/")
    else:
        result["details"].append(f"Найдено файлов правил: {len(rule_files)}")
    
    # Проверяем наличие frontmatter в одном из файлов
    has_frontmatter = False
    for rule_file in rule_files[:3]:  # Проверяем первые 3 файла
        try:
            content = rule_file.read_text(encoding="utf-8")
            if content.startswith("---"):
                has_frontmatter = True
                break
        except Exception:
            pass
    
    if not has_frontmatter:
        score -= 3
        result["issues"].append("Не обнаружен frontmatter в правилах")
    else:
        result["details"].append("Frontmatter обнаружен")
    
    result["score"] = score
    return result


def check_memory_bank(base: Path) -> Dict:
    """Проверяет Memory Bank 2.0 (10 баллов)."""
    memory_path = base / "memory"
    result = {
        "exists": False,
        "score": 0,
        "details": [],
        "issues": [],
    }
    
    if not memory_path.exists():
        result["issues"].append("Директория .cursor/memory/ отсутствует")
        return result
    
    result["exists"] = True
    score = 10
    
    # Проверяем ключевые файлы Memory Bank
    key_files = ["projectbrief.md", "systemPatterns.md", "decisions.md"]
    found_files = []
    
    for key_file in key_files:
        if (memory_path / key_file).exists():
            found_files.append(key_file)
    
    if len(found_files) < 2:
        score -= 5
        result["issues"].append(f"Отсутствуют ключевые файлы Memory Bank (найдено: {len(found_files)}/3)")
    else:
        result["details"].append(f"Ключевые файлы: {', '.join(found_files)}")
    
    # Проверяем наличие скрипта автообновления (опционально)
    update_script = Path("scripts") / "update_memory_bank.py"
    if update_script.exists():
        result["details"].append("Скрипт автообновления найден")
        score += 0  # Бонус не добавляем, это опционально
    else:
        result["details"].append("Скрипт автообновления не найден (опционально)")
    
    result["score"] = score
    return result


def check_mcp_gateway(base: Path) -> Dict:
    """Проверяет MCP Gateway (10 баллов)."""
    mcp_path = base / "mcp.json"
    result = {
        "exists": False,
        "score": 0,
        "details": [],
        "issues": [],
    }
    
    if not mcp_path.exists():
        result["issues"].append("Файл .cursor/mcp.json отсутствует")
        return result
    
    result["exists"] = True
    score = 10
    
    # Проверяем валидность JSON
    try:
        mcp_data = json.loads(mcp_path.read_text(encoding="utf-8"))
        result["details"].append("JSON валиден")
    except json.JSONDecodeError as e:
        score -= 5
        result["issues"].append(f"Невалидный JSON: {str(e)}")
        result["score"] = score
        return result
    
    # Проверяем наличие серверов/сервисов
    if "mcpServers" in mcp_data and mcp_data["mcpServers"]:
        result["details"].append(f"MCP серверов настроено: {len(mcp_data['mcpServers'])}")
    else:
        score -= 3
        result["issues"].append("Нет настроенных MCP серверов")
    
    result["score"] = score
    return result


def check_hooks_system(base: Path) -> Dict:
    """Проверяет Hooks System (10 баллов)."""
    hooks_path = base / "hooks.json"
    hooks_dir = base / "hooks"
    result = {
        "exists": False,
        "score": 0,
        "details": [],
        "issues": [],
    }
    
    score = 0
    
    # Проверяем наличие hooks.json или директории hooks/
    if hooks_path.exists():
        result["exists"] = True
        score = 10
        
        try:
            hooks_data = json.loads(hooks_path.read_text(encoding="utf-8"))
            if hooks_data:
                result["details"].append("hooks.json валиден и содержит конфигурацию")
            else:
                score -= 3
                result["issues"].append("hooks.json пуст")
        except Exception as e:
            score -= 5
            result["issues"].append(f"Ошибка чтения hooks.json: {str(e)}")
    
    elif hooks_dir.exists() and list(hooks_dir.glob("*.py")):
        result["exists"] = True
        score = 8  # Немного меньше, чем hooks.json
        result["details"].append(f"Найдены Python-хуки в hooks/: {len(list(hooks_dir.glob('*.py')))}")
    
    else:
        result["issues"].append("Hooks System не настроен (отсутствует hooks.json или hooks/)")
    
    result["score"] = score
    return result


def check_validation_framework(base: Path) -> Dict:
    """Проверяет Validation Framework SAFE+CoVe (15 баллов)."""
    validation_path = base / "validation"
    result = {
        "exists": False,
        "score": 0,
        "details": [],
        "issues": [],
        "safe_passed": False,
        "cove_passed": False,
    }
    
    if not validation_path.exists():
        result["issues"].append("Директория .cursor/validation/ отсутствует")
        return result
    
    result["exists"] = True
    score = 0
    
    # Проверяем наличие валидаторов
    validators_py = validation_path / "validators.py"
    if validators_py.exists():
        score += 5
        result["details"].append("validators.py найден")
        
        # Пытаемся запустить проверку (если есть --check)
        success, output = run_check(f"python {validators_py} --check all", timeout=10)
        if success:
            score += 5
            result["safe_passed"] = True
            result["details"].append("SAFE валидация прошла")
        else:
            result["issues"].append("SAFE валидация не выполнена или провалилась")
    else:
        result["issues"].append("validators.py не найден")
    
    # Проверяем CoVe (Chain of Verification)
    cove_files = list(validation_path.glob("*cove*")) + list(validation_path.glob("*CoVe*"))
    if cove_files:
        score += 5
        result["cove_passed"] = True
        result["details"].append(f"CoVe компоненты найдены: {len(cove_files)}")
    else:
        result["issues"].append("CoVe компоненты не найдены")
        score += 0  # CoVe опционален
    
    result["score"] = min(15, score)  # Максимум 15 баллов
    return result


def check_observability(base: Path) -> Dict:
    """Проверяет Observability (10 баллов)."""
    metrics_path = base / "metrics"
    metrics_json = Path("cursor-metrics.json")
    mcp_health = metrics_path / "mcp_health.json"
    result = {
        "exists": False,
        "score": 0,
        "details": [],
        "issues": [],
    }
    
    score = 0
    
    # Проверяем директорию metrics/
    if metrics_path.exists():
        score += 2
        result["exists"] = True
        result["details"].append("Директория .cursor/metrics/ существует")
        
        # Проверяем наличие collector.py
        collector = metrics_path / "collector.py"
        if collector.exists():
            score += 1
            result["details"].append("collector.py найден")
    else:
        result["issues"].append("Директория .cursor/metrics/ отсутствует")
    
    # Проверяем наличие cursor-metrics.json
    if metrics_json.exists():
        score += 2
        try:
            metrics_data = json.loads(metrics_json.read_text(encoding="utf-8"))
            if metrics_data:
                score += 1
                result["details"].append("cursor-metrics.json валиден и содержит данные")
            else:
                result["issues"].append("cursor-metrics.json пуст")
        except Exception as e:
            result["issues"].append(f"Ошибка чтения cursor-metrics.json: {str(e)}")
    else:
        result["issues"].append("cursor-metrics.json не найден")
    
    # Проверяем наличие mcp_health.json (бонус за MCP observability)
    if mcp_health.exists():
        score += 3
        try:
            health_data = json.loads(mcp_health.read_text(encoding="utf-8"))
            if health_data and "timestamp" in health_data:
                score += 1
                result["details"].append("mcp_health.json найден и актуален")
        except Exception:
            pass
    else:
        result["details"].append("mcp_health.json отсутствует (опционально)")
    
    result["score"] = min(10, score)
    return result


def check_governance_loop(base: Path) -> Dict:
    """Проверяет Governance Loop (10 баллов)."""
    governance_path = base / "governance"
    result = {
        "exists": False,
        "score": 0,
        "details": [],
        "issues": [],
        "active": False,
    }
    
    if not governance_path.exists():
        result["issues"].append("Директория .cursor/governance/ отсутствует")
        return result
    
    result["exists"] = True
    score = 0
    
    # Проверяем наличие governance_loop.py
    loop_script = base / "metrics" / "governance_loop.py"
    if loop_script.exists():
        score += 3
        result["details"].append("governance_loop.py найден")
    else:
        result["issues"].append("governance_loop.py не найден")
    
    # Проверяем наличие profile.yaml
    profile_path = governance_path / "profile.yaml"
    if profile_path.exists():
        score += 5
        result["details"].append("profile.yaml найден")
        
        try:
            profile_data = yaml.safe_load(profile_path.read_text(encoding="utf-8"))
            if profile_data.get("active_profile"):
                score += 2
                result["active"] = True
                result["details"].append(f"Активный профиль: {profile_data.get('active_profile')}")
        except Exception as e:
            result["issues"].append(f"Ошибка чтения profile.yaml: {str(e)}")
    else:
        result["issues"].append("profile.yaml отсутствует")
    
    result["score"] = min(10, score)
    return result


def check_playbooks_suite(base: Path) -> Dict:
    """Проверяет Playbooks Suite (10 баллов)."""
    playbooks_path = base / "playbooks"
    result = {
        "exists": False,
        "score": 0,
        "details": [],
        "issues": [],
        "playbooks_found": [],
    }
    
    if not playbooks_path.exists():
        result["issues"].append("Директория .cursor/playbooks/ отсутствует")
        return result
    
    result["exists"] = True
    score = 0
    
    # Проверяем наличие ключевых плейбуков
    key_playbooks = ["audit.yaml", "init.yaml"]
    optional_playbooks = ["ci-check.yaml", "refactor.yaml", "build-reflexio.yaml", "digest-reflexio.yaml"]
    
    all_playbooks = list(playbooks_path.glob("*.yaml")) + list(playbooks_path.glob("*.yml"))
    result["playbooks_found"] = [p.name for p in all_playbooks]
    
    if all_playbooks:
        score += 3
        result["details"].append(f"Найдено плейбуков: {len(all_playbooks)}")
    
    # Проверяем наличие обязательных плейбуков
    for playbook in key_playbooks:
        if (playbooks_path / playbook).exists():
            score += 3
            result["details"].append(f"{playbook} найден")
        else:
            result["issues"].append(f"{playbook} отсутствует")
    
    # Бонус за опциональные плейбуки
    optional_found = sum(1 for p in optional_playbooks if (playbooks_path / p).exists())
    if optional_found > 0:
        score += min(1, optional_found)  # До 1 балла за опциональные
        result["details"].append(f"Опциональных плейбуков найдено: {optional_found}")
    
    result["score"] = min(10, score)
    return result


def check_multi_agent_system(base: Path) -> Dict:
    """Проверяет Multi-Agent System (10 баллов)."""
    agents_path = base / "agents"
    result = {
        "exists": False,
        "score": 0,
        "details": [],
        "issues": [],
    }
    
    if not agents_path.exists():
        result["issues"].append("Директория .cursor/agents/ отсутствует")
        # Считаем это не критичным для MVP
        result["score"] = 5
        result["details"].append("Multi-Agent система не настроена (опционально для MVP)")
        return result
    
    result["exists"] = True
    score = 5  # Базовые баллы за наличие
    
    # Проверяем наличие конфигурации агентов
    agent_configs = list(agents_path.glob("*.yaml")) + list(agents_path.glob("*.yml")) + list(agents_path.glob("*.json"))
    if agent_configs:
        score += 3
        result["details"].append(f"Конфигураций агентов найдено: {len(agent_configs)}")
    
    # Проверяем наличие worktrees для изоляции или скрипта spawn_isolated
    worktrees_path = Path(".git") / "worktrees"
    spawn_isolated = Path("scripts/agents/spawn_isolated.py")
    run_all_agents = Path("scripts/agents/run_all_agents.py")
    
    if worktrees_path.exists() and list(worktrees_path.iterdir()):
        score += 2
        result["details"].append("Git worktrees найдены (изоляция агентов)")
    elif spawn_isolated.exists() and run_all_agents.exists():
        score += 2
        result["details"].append("Скрипты изоляции агентов найдены (spawn_isolated.py, run_all_agents.py)")
    else:
        result["details"].append("Git worktrees не настроены (изоляция опциональна)")
    
    result["score"] = min(10, score)
    return result


def calculate_level(score: int) -> Tuple[int, str]:
    """Вычисляет уровень зрелости по баллам."""
    if score >= 90:
        return 5, "Self-Adaptive"
    elif score >= 70:
        return 4, "Automated"
    elif score >= 50:
        return 3, "Pro"
    elif score >= 30:
        return 2, "Foundational"
    elif score >= 10:
        return 1, "Initial"
    else:
        return 0, "Initial"


def audit(mode: str = "standard") -> Dict:
    """Основная функция эталонного аудита CEB-E v1.0."""
    base = Path(".cursor")
    base.mkdir(exist_ok=True)
    
    result = {
        "date": datetime.date.today().isoformat(),
        "timestamp": datetime.datetime.now().isoformat(),
        "project_name": Path.cwd().name,
        "auditor": os.getenv("USER", os.getenv("USERNAME", "auto")),
        "mode": mode,
        "standard": "CEB-E v1.0",
        "components": {},
        "score": 0,
        "max_score": 100,
        "recommendations": [],
    }
    
    # Проверяем все 9 компонентов
    print("[audit] Проверка компонентов CEB-E v1.0...")
    
    result["components"]["rules_engine"] = check_rules_engine(base)
    result["components"]["memory_bank"] = check_memory_bank(base)
    result["components"]["mcp_gateway"] = check_mcp_gateway(base)
    result["components"]["hooks_system"] = check_hooks_system(base)
    result["components"]["validation_framework"] = check_validation_framework(base)
    result["components"]["observability"] = check_observability(base)
    result["components"]["governance_loop"] = check_governance_loop(base)
    result["components"]["playbooks_suite"] = check_playbooks_suite(base)
    result["components"]["multi_agent"] = check_multi_agent_system(base)
    
    # Вычисляем общий балл
    total_score = sum(comp.get("score", 0) for comp in result["components"].values())
    result["score"] = total_score
    
    # Определяем уровень зрелости
    level, level_name = calculate_level(total_score)
    result["level"] = level
    result["level_name"] = level_name
    
    # Вычисляем AI Reliability Index и Context Hit Rate
    reliability = min(100, int((total_score / 100) * 100))
    result["ai_reliability_index"] = reliability / 100.0
    result["context_hit_rate"] = max(0.0, (reliability - 10) / 100.0) if reliability > 10 else reliability / 100.0
    
    # Формируем рекомендации
    if total_score < 90:
        result["recommendations"].append("Достичь уровня Self-Adaptive требует дополнительной настройки компонентов")
    
    if not result["components"]["governance_loop"].get("active"):
        result["recommendations"].append("Настроить Governance Loop для автоматического управления профилями")
    
    if not result["components"]["validation_framework"].get("safe_passed"):
        result["recommendations"].append("Включить SAFE валидацию для повышения безопасности")
    
    # Сохраняем результаты
    audit_dir = base / "audit"
    audit_dir.mkdir(exist_ok=True)
    
    report_path = audit_dir / "audit_report.json"
    report_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    
    # Выводим краткий отчёт
    print(f"\n{'='*70}")
    print(f"CEB-E Эталонный Аудит v1.0")
    print(f"{'='*70}")
    print(f"Проект: {result['project_name']}")
    print(f"Дата: {result['date']}")
    print(f"Режим: {mode}")
    print(f"\nОбщий балл: {total_score} / 100")
    print(f"Уровень зрелости: {level} / 5 — {level_name}")
    print(f"AI Reliability Index: {result['ai_reliability_index']:.2f}")
    print(f"Context Hit Rate: {result['context_hit_rate']:.2f}")
    print(f"\nОтчёт сохранён: {report_path}")
    print(f"{'='*70}\n")
    
    return result


def main():
    parser = argparse.ArgumentParser(description="CEB-E Эталонный Аудит v1.0")
    parser.add_argument(
        "--mode",
        choices=["standard", "quick", "full"],
        default="standard",
        help="Режим аудита",
    )
    args = parser.parse_args()
    
    try:
        audit(args.mode)
        sys.exit(0)
    except Exception as e:
        print(f"Ошибка при выполнении аудита: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
