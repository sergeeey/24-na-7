#!/usr/bin/env python3
"""
Scheduler — автономный планировщик задач для Reflexio 24/7.
Выполняет периодические проверки, аудиты и метрики.
"""
import sys
import time
import subprocess
import signal
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, Any
import json

sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from src.utils.logging import setup_logging, get_logger
    setup_logging()
    logger = get_logger("scheduler")
except Exception:
    import logging
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger("scheduler")


class TaskScheduler:
    """Планировщик задач для Reflexio."""
    
    def __init__(self):
        self.running = True
        self.last_runs: Dict[str, datetime] = {}
        self.log_dir = Path(".cursor/logs")
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.log_file = self.log_dir / "scheduler.log"
        
        # Регистрируем обработчик сигналов
        signal.signal(signal.SIGTERM, self._handle_signal)
        signal.signal(signal.SIGINT, self._handle_signal)
    
    def _handle_signal(self, signum, frame):
        """Обработчик сигналов для graceful shutdown."""
        logger.info("scheduler_shutdown_signal", signal=signum)
        self.running = False
    
    def log(self, message: str, level: str = "INFO"):
        """Записывает сообщение в лог."""
        timestamp = datetime.now().isoformat()
        log_entry = f"[{timestamp}] [{level}] {message}\n"
        
        try:
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(log_entry)
        except Exception as e:
            print(f"Failed to write log: {e}")
        
        if level == "ERROR":
            logger.error(message)
        elif level == "WARNING":
            logger.warning(message)
        else:
            logger.info(message)
    
    def should_run(self, task_name: str, interval_hours: float) -> bool:
        """Проверяет, нужно ли запускать задачу."""
        now = datetime.now()
        last_run = self.last_runs.get(task_name)
        
        if last_run is None:
            return True
        
        time_since_last = now - last_run
        return time_since_last >= timedelta(hours=interval_hours)
    
    def run_playbook(self, playbook_name: str, timeout: int = 3600) -> bool:
        """Запускает playbook."""
        try:
            self.log(f"Running playbook: {playbook_name}")
            
            # Используем прямой вызов Python скрипта или playbook команду
            # В зависимости от реализации playbooks
            result = subprocess.run(
                ["python", "-m", "cursor.playbooks", playbook_name],
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            
            if result.returncode == 0:
                self.log(f"Playbook {playbook_name} completed successfully")
                return True
            else:
                self.log(f"Playbook {playbook_name} failed: {result.stderr}", level="ERROR")
                return False
                
        except subprocess.TimeoutExpired:
            self.log(f"Playbook {playbook_name} timed out after {timeout}s", level="ERROR")
            return False
        except Exception as e:
            self.log(f"Error running playbook {playbook_name}: {e}", level="ERROR")
            return False
    
    def run_validate_level5(self):
        """Запускает валидацию Level 5 (каждые 6 часов)."""
        if not self.should_run("validate-level5", 6.0):
            return
        
        self.log("Starting validate-level5 check")
        
        # Запускаем валидацию через скрипт
        try:
            result = subprocess.run(
                ["python", ".cursor/validation/level5_validation.py"],
                capture_output=True,
                text=True,
                timeout=600,
            )
            
            if result.returncode == 0:
                self.log("validate-level5 completed successfully")
            else:
                self.log(f"validate-level5 failed: {result.stderr}", level="WARNING")
        except Exception as e:
            self.log(f"Error running validate-level5: {e}", level="ERROR")
        
        self.last_runs["validate-level5"] = datetime.now()
    
    def run_proxy_diagnostics(self):
        """Запускает диагностику прокси (раз в день)."""
        if not self.should_run("proxy-diagnostics", 24.0):
            return
        
        self.log("Starting proxy-diagnostics check")
        
        try:
            result = subprocess.run(
                ["python", "-c", "from pathlib import Path; import sys; sys.path.insert(0, str(Path.cwd())); from .cursor.playbooks.proxy_diagnostics import main; main()"],
                capture_output=True,
                text=True,
                timeout=300,
            )
            
            if result.returncode == 0:
                self.log("proxy-diagnostics completed successfully")
            else:
                self.log(f"proxy-diagnostics warning: {result.stderr}", level="WARNING")
        except Exception as e:
            self.log(f"Error running proxy-diagnostics: {e}", level="ERROR")
        
        self.last_runs["proxy-diagnostics"] = datetime.now()
    
    def run_audit(self):
        """Запускает аудит (раз в неделю)."""
        if not self.should_run("audit", 168.0):  # 7 дней
            return
        
        self.log("Starting weekly audit")
        
        try:
            result = subprocess.run(
                ["python", ".cursor/audit/run_audit.py", "--mode", "standard"],
                capture_output=True,
                text=True,
                timeout=1800,
            )
            
            if result.returncode == 0:
                self.log("Audit completed successfully")
                
                # Применяем результаты через governance loop
                subprocess.run(
                    ["python", ".cursor/metrics/governance_loop.py", "--apply", "results"],
                    timeout=60,
                )
            else:
                self.log(f"Audit failed: {result.stderr}", level="ERROR")
        except Exception as e:
            self.log(f"Error running audit: {e}", level="ERROR")
        
        self.last_runs["audit"] = datetime.now()
    
    def run_observability_setup(self):
        """Запускает проверку observability (при старте)."""
        if "observability-setup" in self.last_runs:
            return
        
        self.log("Running observability-setup on startup")
        
        try:
            # Простая проверка наличия конфигов
            prometheus = Path("observability/prometheus.yml").exists()
            alerts = Path("observability/alert_rules.yml").exists()
            grafana = Path("observability/grafana_dashboards/reflexio.json").exists()
            
            if prometheus and alerts and grafana:
                self.log("Observability configs found")
            else:
                self.log("Observability configs missing", level="WARNING")
        except Exception as e:
            self.log(f"Error checking observability: {e}", level="ERROR")
        
        self.last_runs["observability-setup"] = datetime.now()
    
    def run_loop(self):
        """Основной цикл планировщика."""
        self.log("Scheduler started", level="INFO")
        
        # Запускаем observability setup при старте
        self.run_observability_setup()
        
        # Основной цикл
        while self.running:
            try:
                # Валидация Level 5 каждые 6 часов
                self.run_validate_level5()
                
                # Диагностика прокси раз в день
                self.run_proxy_diagnostics()
                
                # Аудит раз в неделю
                self.run_audit()
                
                # Ждём 1 час перед следующей проверкой
                time.sleep(3600)
                
            except KeyboardInterrupt:
                self.log("Scheduler interrupted by user")
                break
            except Exception as e:
                self.log(f"Error in scheduler loop: {e}", level="ERROR")
                time.sleep(60)  # Ждём минуту перед повтором
        
        self.log("Scheduler stopped")


def main():
    """Точка входа."""
    scheduler = TaskScheduler()
    scheduler.run_loop()


if __name__ == "__main__":
    main()











