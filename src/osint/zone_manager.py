"""
Zone Manager — управление зональными прокси Bright Data.

Поддерживает разные зоны для разных типов миссий и авто-ротацию IP.
"""
import json
import sys
from pathlib import Path
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

try:
    from src.utils.logging import setup_logging, get_logger
    setup_logging()
    logger = get_logger("osint.zones")
except Exception:
    import logging
    logger = logging.getLogger("osint.zones")


class ZoneManager:
    """Менеджер зон Bright Data для ротации и выбора оптимальных зон."""
    
    def __init__(self, zones_config_path: Optional[Path] = None):
        """
        Инициализация менеджера зон.
        
        Args:
            zones_config_path: Путь к конфигурации зон (JSON)
        """
        self.zones_config_path = zones_config_path or Path(".cursor/config/brightdata_zones.json")
        self.zones_config = self._load_zones_config()
        self.zone_usage = {}  # Отслеживание использования зон
        self.rotation_enabled = True
    
    def _load_zones_config(self) -> Dict[str, Any]:
        """Загружает конфигурацию зон."""
        if not self.zones_config_path.exists():
            # Создаём конфигурацию по умолчанию
            default_config = {
                "zones": {
                    "serp_api1": {
                        "name": "SERP API Zone 1",
                        "type": "serp",
                        "engines": ["google", "bing"],
                        "priority": 1,
                        "rotation_enabled": True,
                    },
                    "news": {
                        "name": "News Zone",
                        "type": "content",
                        "engines": [],
                        "priority": 2,
                        "rotation_enabled": True,
                    },
                    "academic": {
                        "name": "Academic Zone",
                        "type": "content",
                        "engines": [],
                        "priority": 3,
                        "rotation_enabled": False,
                    },
                },
                "rotation": {
                    "enabled": True,
                    "method": "round_robin",  # "round_robin", "least_used", "random"
                },
            }
            
            self.zones_config_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.zones_config_path, "w", encoding="utf-8") as f:
                json.dump(default_config, f, indent=2, ensure_ascii=False)
            
            logger.info("zones_config_created", path=str(self.zones_config_path))
            return default_config
        
        try:
            with open(self.zones_config_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error("zones_config_load_failed", error=str(e))
            return {}
    
    def get_zone_for_mission(self, mission_type: str = "general") -> Optional[str]:
        """
        Выбирает оптимальную зону для миссии.
        
        Args:
            mission_type: Тип миссии ("serp", "news", "academic", "general")
            
        Returns:
            Имя зоны или None
        """
        zones = self.zones_config.get("zones", {})
        
        # Ищем зону по типу миссии
        suitable_zones = [
            (name, config)
            for name, config in zones.items()
            if config.get("type") == mission_type or mission_type == "general"
        ]
        
        if not suitable_zones:
            # Fallback: используем зону по умолчанию
            import os
            default_zone = os.getenv("BRIGHTDATA_ZONE", "serp_api1")
            logger.warning("no_zone_for_mission_type", mission_type=mission_type, using_default=default_zone)
            return default_zone
        
        # Сортируем по приоритету
        suitable_zones.sort(key=lambda x: x[1].get("priority", 999))
        
        # Выбираем зону в зависимости от метода ротации
        rotation_method = self.zones_config.get("rotation", {}).get("method", "round_robin")
        
        if rotation_method == "least_used":
            # Выбираем наименее используемую зону
            zone_name = min(suitable_zones, key=lambda x: self.zone_usage.get(x[0], 0))[0]
        elif rotation_method == "random":
            import random
            zone_name = random.choice(suitable_zones)[0]
        else:
            # Round-robin: выбираем первую доступную
            zone_name = suitable_zones[0][0]
        
        # Обновляем статистику использования
        self.zone_usage[zone_name] = self.zone_usage.get(zone_name, 0) + 1
        
        logger.debug("zone_selected", zone=zone_name, mission_type=mission_type, usage_count=self.zone_usage[zone_name])
        
        return zone_name
    
    def get_zone_for_engine(self, search_engine: str) -> Optional[str]:
        """
        Выбирает зону для конкретной поисковой системы.
        
        Args:
            search_engine: Поисковая система ("google", "bing", "yahoo")
            
        Returns:
            Имя зоны
        """
        zones = self.zones_config.get("zones", {})
        
        # Ищем зону, которая поддерживает эту поисковую систему
        for zone_name, config in zones.items():
            engines = config.get("engines", [])
            if search_engine in engines:
                self.zone_usage[zone_name] = self.zone_usage.get(zone_name, 0) + 1
                return zone_name
        
        # Fallback: зона по умолчанию
        import os
        default_zone = os.getenv("BRIGHTDATA_ZONE", "serp_api1")
        logger.debug("zone_fallback", engine=search_engine, zone=default_zone)
        return default_zone
    
    def save_usage_stats(self, stats_path: Optional[Path] = None):
        """Сохраняет статистику использования зон."""
        stats_path = stats_path or Path(".cursor/metrics/zone_usage_stats.json")
        
        stats = {
            "last_updated": datetime.now(timezone.utc).isoformat(),
            "usage": self.zone_usage,
            "total_requests": sum(self.zone_usage.values()),
        }
        
        stats_path.parent.mkdir(parents=True, exist_ok=True)
        with open(stats_path, "w", encoding="utf-8") as f:
            json.dump(stats, f, indent=2, ensure_ascii=False)
        
        logger.debug("zone_usage_stats_saved", path=str(stats_path))


def get_zone_manager() -> ZoneManager:
    """Фабрика для создания ZoneManager."""
    return ZoneManager()


# Глобальный экземпляр для переиспользования
_zone_manager: Optional[ZoneManager] = None


def get_zone_for_mission(mission_type: str = "general") -> Optional[str]:
    """Быстрый доступ к выбору зоны."""
    global _zone_manager
    if _zone_manager is None:
        _zone_manager = ZoneManager()
    return _zone_manager.get_zone_for_mission(mission_type)


def get_zone_for_engine(search_engine: str) -> Optional[str]:
    """Быстрый доступ к выбору зоны для поисковой системы."""
    global _zone_manager
    if _zone_manager is None:
        _zone_manager = ZoneManager()
    return _zone_manager.get_zone_for_engine(search_engine)

