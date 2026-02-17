"""
Live Monitoring Agent — автоматическое обновление OSINT миссий по расписанию.

Поддерживает периодический запуск миссий и мониторинг изменений в данных.
"""
import json
import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.osint.pemm_agent import run_osint_mission, load_mission

try:
    from src.utils.logging import setup_logging, get_logger
    setup_logging()
    logger = get_logger("osint.monitoring")
except Exception:
    import logging
    logger = logging.getLogger("osint.monitoring")


class MonitoringSchedule:
    """Расписание для мониторинга миссий."""
    
    def __init__(
        self,
        mission_id: str,
        mission_path: Path,
        interval_hours: int = 24,
        enabled: bool = True,
        last_run: Optional[str] = None,
    ):
        self.mission_id = mission_id
        self.mission_path = mission_path
        self.interval_hours = interval_hours
        self.enabled = enabled
        self.last_run = last_run
    
    def should_run(self) -> bool:
        """Проверяет, нужно ли запускать миссию."""
        if not self.enabled:
            return False
        
        if not self.last_run:
            return True
        
        try:
            last_run_dt = datetime.fromisoformat(self.last_run.replace("Z", "+00:00"))
            next_run = last_run_dt + timedelta(hours=self.interval_hours)
            return datetime.now(timezone.utc) >= next_run
        except Exception:
            return True
    
    def mark_run(self):
        """Отмечает время последнего запуска."""
        self.last_run = datetime.now(timezone.utc).isoformat()
    
    def to_dict(self) -> Dict[str, Any]:
        """Конвертирует в словарь для сохранения."""
        return {
            "mission_id": self.mission_id,
            "mission_path": str(self.mission_path),
            "interval_hours": self.interval_hours,
            "enabled": self.enabled,
            "last_run": self.last_run,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MonitoringSchedule":
        """Создаёт из словаря."""
        return cls(
            mission_id=data["mission_id"],
            mission_path=Path(data["mission_path"]),
            interval_hours=data.get("interval_hours", 24),
            enabled=data.get("enabled", True),
            last_run=data.get("last_run"),
        )


class MonitoringAgent:
    """Агент для автоматического мониторинга OSINT миссий."""
    
    def __init__(self, schedule_file: Path = Path(".cursor/osint/monitoring_schedule.json")):
        self.schedule_file = schedule_file
        self.schedules: List[MonitoringSchedule] = []
        self.load_schedules()
    
    def load_schedules(self):
        """Загружает расписания из файла."""
        if not self.schedule_file.exists():
            self.schedules = []
            return
        
        try:
            with open(self.schedule_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            self.schedules = [
                MonitoringSchedule.from_dict(item) for item in data.get("schedules", [])
            ]
            
            logger.info("monitoring_schedules_loaded", count=len(self.schedules))
            
        except Exception as e:
            logger.error("schedule_load_failed", error=str(e))
            self.schedules = []
    
    def save_schedules(self):
        """Сохраняет расписания в файл."""
        try:
            self.schedule_file.parent.mkdir(parents=True, exist_ok=True)
            
            data = {
                "schedules": [s.to_dict() for s in self.schedules],
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            
            with open(self.schedule_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            
            logger.debug("monitoring_schedules_saved")
            
        except Exception as e:
            logger.error("schedule_save_failed", error=str(e))
    
    def register_mission(
        self,
        mission_path: Path,
        interval_hours: int = 24,
        enabled: bool = True,
    ):
        """
        Регистрирует миссию для автоматического мониторинга.
        
        Args:
            mission_path: Путь к файлу миссии
            interval_hours: Интервал запуска в часах
            enabled: Включён ли мониторинг
        """
        try:
            mission = load_mission(mission_path)
            mission_id = mission.id
            
            # Проверяем, есть ли уже расписание для этой миссии
            existing = next(
                (s for s in self.schedules if s.mission_id == mission_id),
                None
            )
            
            if existing:
                existing.interval_hours = interval_hours
                existing.enabled = enabled
                logger.info("monitoring_schedule_updated", mission_id=mission_id)
            else:
                schedule = MonitoringSchedule(
                    mission_id=mission_id,
                    mission_path=mission_path,
                    interval_hours=interval_hours,
                    enabled=enabled,
                )
                self.schedules.append(schedule)
                logger.info("monitoring_schedule_registered", mission_id=mission_id)
            
            self.save_schedules()
            
        except Exception as e:
            logger.error("mission_registration_failed", path=str(mission_path), error=str(e))
    
    def run_due_missions(self) -> List[Dict[str, Any]]:
        """
        Запускает все миссии, которые должны быть выполнены.
        
        Returns:
            Список результатов выполнения миссий
        """
        results = []
        
        logger.info("checking_due_missions", total_schedules=len(self.schedules))
        
        for schedule in self.schedules:
            if not schedule.should_run():
                continue
            
            try:
                logger.info("running_scheduled_mission", mission_id=schedule.mission_id)
                
                mission = load_mission(schedule.mission_path)
                result = run_osint_mission(mission)
                
                schedule.mark_run()
                
                results.append({
                    "mission_id": schedule.mission_id,
                    "result": result,
                    "status": "success",
                })
                
                logger.info(
                    "scheduled_mission_completed",
                    mission_id=schedule.mission_id,
                    claims=result.total_claims,
                    confidence=result.avg_confidence,
                )
                
            except Exception as e:
                logger.error(
                    "scheduled_mission_failed",
                    mission_id=schedule.mission_id,
                    error=str(e),
                )
                
                results.append({
                    "mission_id": schedule.mission_id,
                    "status": "failed",
                    "error": str(e),
                })
        
        self.save_schedules()
        
        return results
    
    def list_schedules(self) -> List[Dict[str, Any]]:
        """Возвращает список всех расписаний."""
        return [
            {
                "mission_id": s.mission_id,
                "interval_hours": s.interval_hours,
                "enabled": s.enabled,
                "last_run": s.last_run,
                "next_run": self._calculate_next_run(s),
            }
            for s in self.schedules
        ]
    
    def _calculate_next_run(self, schedule: MonitoringSchedule) -> Optional[str]:
        """Вычисляет время следующего запуска."""
        if not schedule.last_run:
            return "immediately"
        
        try:
            last_run_dt = datetime.fromisoformat(schedule.last_run.replace("Z", "+00:00"))
            next_run = last_run_dt + timedelta(hours=schedule.interval_hours)
            return next_run.isoformat()
        except Exception:
            return None


def main():
    """CLI для Monitoring Agent."""
    import argparse
    
    parser = argparse.ArgumentParser(description="OSINT Live Monitoring Agent")
    parser.add_argument(
        "action",
        choices=["run", "register", "list"],
        help="Действие: run (запустить), register (зарегистрировать), list (список)",
    )
    parser.add_argument(
        "--mission",
        type=Path,
        help="Путь к файлу миссии (для register)",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=24,
        help="Интервал в часах (для register)",
    )
    
    args = parser.parse_args()
    
    agent = MonitoringAgent()
    
    if args.action == "run":
        results = agent.run_due_missions()
        
        print("\n" + "=" * 70)
        print("Monitoring Agent — Run Results")
        print("=" * 70)
        print(f"Missions executed: {len(results)}")
        
        for result in results:
            if result["status"] == "success":
                r = result["result"]
                print(f"\n✅ {result['mission_id']}")
                print(f"   Claims: {r.total_claims} (validated: {r.validated_claims})")
                print(f"   Avg confidence: {r.avg_confidence:.2f}")
            else:
                print(f"\n❌ {result['mission_id']}: {result.get('error', 'Unknown error')}")
        
        print("=" * 70 + "\n")
    
    elif args.action == "register":
        if not args.mission:
            print("Error: --mission required for register action")
            return 1
        
        agent.register_mission(args.mission, interval_hours=args.interval)
        print(f"✅ Mission registered: {args.mission}")
    
    elif args.action == "list":
        schedules = agent.list_schedules()
        
        print("\n" + "=" * 70)
        print("Monitoring Agent — Schedules")
        print("=" * 70)
        
        if not schedules:
            print("No scheduled missions.")
        else:
            for s in schedules:
                status = "✅ Enabled" if s["enabled"] else "⏸️  Disabled"
                print(f"\n{status}: {s['mission_id']}")
                print(f"   Interval: {s['interval_hours']} hours")
                print(f"   Last run: {s['last_run'] or 'Never'}")
                print(f"   Next run: {s['next_run'] or 'Unknown'}")
        
        print("=" * 70 + "\n")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())













