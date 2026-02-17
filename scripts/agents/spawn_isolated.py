#!/usr/bin/env python3
"""
Изолированный запуск агентов через Git worktrees.

Создаёт изолированное окружение для каждого агента, предотвращая конфликты.
"""
import sys
import os
import subprocess
import shutil
from pathlib import Path
from typing import Optional, Dict, Any
import argparse
import json
from datetime import datetime


def create_worktree(agent_name: str, base_path: Path = None) -> Path:
    """
    Создаёт Git worktree для изолированного запуска агента.
    
    Args:
        agent_name: Имя агента
        base_path: Базовый путь проекта
        
    Returns:
        Путь к worktree
    """
    if base_path is None:
        base_path = Path(__file__).parent.parent.parent
    
    worktrees_dir = base_path / ".cursor" / "worktrees"
    worktrees_dir.mkdir(parents=True, exist_ok=True)
    
    worktree_path = worktrees_dir / agent_name
    
    # Проверяем, существует ли уже worktree
    if worktree_path.exists():
        print(f"⚠️  Worktree для {agent_name} уже существует: {worktree_path}")
        return worktree_path
    
    # Создаём worktree
    try:
        result = subprocess.run(
            ["git", "worktree", "add", str(worktree_path), "HEAD"],
            cwd=base_path,
            capture_output=True,
            text=True,
            check=True
        )
        print(f"✅ Worktree создан: {worktree_path}")
        return worktree_path
    except subprocess.CalledProcessError as e:
        print(f"❌ Ошибка создания worktree: {e.stderr}")
        raise


def remove_worktree(agent_name: str, base_path: Path = None):
    """
    Удаляет Git worktree после завершения работы агента.
    
    Args:
        agent_name: Имя агента
        base_path: Базовый путь проекта
    """
    if base_path is None:
        base_path = Path(__file__).parent.parent.parent
    
    worktrees_dir = base_path / ".cursor" / "worktrees"
    worktree_path = worktrees_dir / agent_name
    
    if not worktree_path.exists():
        print(f"⚠️  Worktree для {agent_name} не найден")
        return
    
    try:
        subprocess.run(
            ["git", "worktree", "remove", str(worktree_path)],
            cwd=base_path,
            capture_output=True,
            check=True
        )
        print(f"✅ Worktree удалён: {worktree_path}")
    except subprocess.CalledProcessError as e:
        print(f"❌ Ошибка удаления worktree: {e.stderr}")
        # Пробуем принудительно удалить
        if worktree_path.exists():
            shutil.rmtree(worktree_path)
            print(f"✅ Worktree принудительно удалён: {worktree_path}")


def run_agent_isolated(
    agent_name: str,
    agent_script: str,
    env_vars: Optional[Dict[str, str]] = None,
    cleanup: bool = True
) -> Dict[str, Any]:
    """
    Запускает агента в изолированном окружении.
    
    Args:
        agent_name: Имя агента
        agent_script: Путь к скрипту агента (относительно worktree)
        env_vars: Дополнительные переменные окружения
        cleanup: Удалять worktree после завершения
        
    Returns:
        Результат выполнения
    """
    base_path = Path(__file__).parent.parent.parent
    worktree_path = create_worktree(agent_name, base_path)
    
    # Подготавливаем окружение
    env = os.environ.copy()
    if env_vars:
        env.update(env_vars)
    
    # Устанавливаем изолированные пути
    env["ISOLATED_AGENT"] = "1"
    env["AGENT_NAME"] = agent_name
    env["WORKTREE_PATH"] = str(worktree_path)
    
    result = {
        "agent_name": agent_name,
        "worktree_path": str(worktree_path),
        "started_at": datetime.now().isoformat(),
        "status": "running",
        "output": "",
        "error": "",
        "exit_code": None,
    }
    
    try:
        # Запускаем агента
        script_path = worktree_path / agent_script
        if not script_path.exists():
            raise FileNotFoundError(f"Скрипт агента не найден: {script_path}")
        
        process = subprocess.Popen(
            [sys.executable, str(script_path)],
            cwd=worktree_path,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        stdout, stderr = process.communicate()
        
        result["status"] = "completed" if process.returncode == 0 else "failed"
        result["exit_code"] = process.returncode
        result["output"] = stdout
        result["error"] = stderr
        result["completed_at"] = datetime.now().isoformat()
        
        if process.returncode == 0:
            print(f"✅ Агент {agent_name} завершён успешно")
        else:
            print(f"❌ Агент {agent_name} завершён с ошибкой (код: {process.returncode})")
        
    except Exception as e:
        result["status"] = "error"
        result["error"] = str(e)
        result["completed_at"] = datetime.now().isoformat()
        print(f"❌ Ошибка запуска агента {agent_name}: {e}")
    
    finally:
        if cleanup:
            remove_worktree(agent_name, base_path)
    
    return result


def list_worktrees(base_path: Path = None) -> list:
    """
    Список всех активных worktrees.
    
    Args:
        base_path: Базовый путь проекта
        
    Returns:
        Список worktrees
    """
    if base_path is None:
        base_path = Path(__file__).parent.parent.parent
    
    try:
        result = subprocess.run(
            ["git", "worktree", "list"],
            cwd=base_path,
            capture_output=True,
            text=True,
            check=True
        )
        return result.stdout.strip().split("\n")
    except subprocess.CalledProcessError:
        return []


def main():
    parser = argparse.ArgumentParser(description="Изолированный запуск агентов")
    parser.add_argument("--agent", required=True, help="Имя агента")
    parser.add_argument("--script", required=True, help="Путь к скрипту агента")
    parser.add_argument("--env", type=str, help="JSON с переменными окружения")
    parser.add_argument("--no-cleanup", action="store_true", help="Не удалять worktree после завершения")
    parser.add_argument("--list", action="store_true", help="Показать список worktrees")
    parser.add_argument("--remove", type=str, help="Удалить worktree для агента")
    
    args = parser.parse_args()
    
    import os
    
    if args.list:
        worktrees = list_worktrees()
        print("Активные worktrees:")
        for wt in worktrees:
            print(f"  {wt}")
        return 0
    
    if args.remove:
        remove_worktree(args.remove)
        return 0
    
    env_vars = None
    if args.env:
        try:
            env_vars = json.loads(args.env)
        except json.JSONDecodeError as e:
            print(f"❌ Ошибка парсинга JSON: {e}")
            return 1
    
    result = run_agent_isolated(
        args.agent,
        args.script,
        env_vars=env_vars,
        cleanup=not args.no_cleanup
    )
    
    # Сохраняем результат
    results_dir = Path(__file__).parent.parent.parent / ".cursor" / "agents" / "results"
    results_dir.mkdir(parents=True, exist_ok=True)
    
    result_file = results_dir / f"{args.agent}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(result_file, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    
    print(f"\nРезультат сохранён: {result_file}")
    
    return 0 if result["status"] == "completed" else 1


if __name__ == "__main__":
    sys.exit(main())
