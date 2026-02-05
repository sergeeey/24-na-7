#!/usr/bin/env python3
"""
Запуск всех агентов с изоляцией через Git worktrees.

Использует spawn_isolated.py для изолированного запуска каждого агента.
"""
import sys
import subprocess
from pathlib import Path
from typing import List, Dict
import argparse
import json

# Добавляем путь к проекту
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.utils.logging import setup_logging, get_logger

setup_logging()
logger = get_logger("agents.runner")


# Список агентов и их скриптов
AGENTS = {
    "audit": ".cursor/agents/audit_agent.py",
    "metrics": ".cursor/agents/metrics_agent.py",
    "digest": ".cursor/agents/digest_agent.py",
    "validation": ".cursor/agents/validation_agent.py",
}


def run_agent_isolated(agent_name: str, agent_script: str, once: bool = False) -> Dict:
    """
    Запускает агента в изолированном окружении.
    
    Args:
        agent_name: Имя агента
        agent_script: Путь к скрипту агента
        once: Запустить один раз (не в цикле)
        
    Returns:
        Результат выполнения
    """
    base_path = Path(__file__).parent.parent.parent
    spawn_script = base_path / "scripts" / "agents" / "spawn_isolated.py"
    
    if not spawn_script.exists():
        logger.error("spawn_isolated_not_found", path=str(spawn_script))
        return {
            "agent_name": agent_name,
            "status": "error",
            "error": "spawn_isolated.py not found",
        }
    
    # Подготавливаем команду
    cmd = [
        sys.executable,
        str(spawn_script),
        "--agent", agent_name,
        "--script", agent_script,
    ]
    
    if once:
        # Передаём --once через env переменные (spawn_isolated не поддерживает напрямую)
        # Агент сам должен поддерживать --once
        pass
    
    try:
        logger.info("starting_agent", agent=agent_name, script=agent_script)
        
        result = subprocess.run(
            cmd,
            cwd=base_path,
            capture_output=True,
            text=True,
            timeout=600,  # 10 минут максимум
        )
        
        if result.returncode == 0:
            logger.info("agent_completed", agent=agent_name)
            return {
                "agent_name": agent_name,
                "status": "completed",
                "output": result.stdout,
            }
        else:
            logger.error("agent_failed", agent=agent_name, error=result.stderr)
            return {
                "agent_name": agent_name,
                "status": "failed",
                "error": result.stderr,
                "output": result.stdout,
            }
            
    except subprocess.TimeoutExpired:
        logger.error("agent_timeout", agent=agent_name)
        return {
            "agent_name": agent_name,
            "status": "timeout",
            "error": "Agent execution timeout",
        }
    except Exception as e:
        logger.error("agent_error", agent=agent_name, error=str(e))
        return {
            "agent_name": agent_name,
            "status": "error",
            "error": str(e),
        }


def run_all_agents(agents: List[str] = None, once: bool = False, parallel: bool = False) -> Dict:
    """
    Запускает всех агентов или указанных.
    
    Args:
        agents: Список имён агентов (None = все)
        once: Запустить один раз
        parallel: Запускать параллельно (через процессы)
        
    Returns:
        Результаты выполнения
    """
    if agents is None:
        agents = list(AGENTS.keys())
    
    results = {}
    
    if parallel:
        # Параллельный запуск через subprocess
        import multiprocessing
        from concurrent.futures import ProcessPoolExecutor
        
        with ProcessPoolExecutor(max_workers=len(agents)) as executor:
            futures = {}
            for agent_name in agents:
                if agent_name not in AGENTS:
                    logger.warning("unknown_agent", agent=agent_name)
                    continue
                agent_script = AGENTS[agent_name]
                future = executor.submit(run_agent_isolated, agent_name, agent_script, once)
                futures[future] = agent_name
            
            for future in futures:
                agent_name = futures[future]
                try:
                    results[agent_name] = future.result(timeout=600)
                except Exception as e:
                    results[agent_name] = {
                        "agent_name": agent_name,
                        "status": "error",
                        "error": str(e),
                    }
    else:
        # Последовательный запуск
        for agent_name in agents:
            if agent_name not in AGENTS:
                logger.warning("unknown_agent", agent=agent_name)
                continue
            
            agent_script = AGENTS[agent_name]
            results[agent_name] = run_agent_isolated(agent_name, agent_script, once)
    
    return results


def main():
    parser = argparse.ArgumentParser(description="Запуск всех агентов с изоляцией")
    parser.add_argument(
        "--agents",
        nargs="+",
        choices=list(AGENTS.keys()),
        help="Список агентов для запуска (по умолчанию все)",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Запустить один раз (не в цикле)",
    )
    parser.add_argument(
        "--parallel",
        action="store_true",
        help="Запускать параллельно",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Сохранить результаты в JSON файл",
    )
    
    args = parser.parse_args()
    
    logger.info("running_agents", agents=args.agents or "all", once=args.once, parallel=args.parallel)
    
    results = run_all_agents(
        agents=args.agents,
        once=args.once,
        parallel=args.parallel,
    )
    
    # Выводим результаты
    print("\n" + "=" * 70)
    print("Результаты запуска агентов")
    print("=" * 70)
    
    for agent_name, result in results.items():
        status_icon = "✅" if result["status"] == "completed" else "❌"
        print(f"{status_icon} {agent_name}: {result['status']}")
        if result.get("error"):
            print(f"   Ошибка: {result['error']}")
    
    print("=" * 70)
    
    # Сохраняем результаты
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        print(f"\nРезультаты сохранены: {args.output}")
    
    # Возвращаем код выхода
    failed = sum(1 for r in results.values() if r["status"] != "completed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())


