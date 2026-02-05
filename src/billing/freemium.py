"""
Freemium модель — 30 мин/день бесплатно.
Reflexio v2.1 — Surpass Smart Noter Sprint
"""
from typing import Dict, Any, Optional
from datetime import date, datetime, timedelta
from pathlib import Path

from src.utils.logging import get_logger
from src.storage.db import get_db

logger = get_logger("billing.freemium")


class FreemiumManager:
    """Управление Freemium моделью."""
    
    def __init__(self, free_minutes_per_day: int = 30):
        """
        Args:
            free_minutes_per_day: Бесплатных минут в день
        """
        self.free_minutes_per_day = free_minutes_per_day
        self.db = get_db()
    
    def check_quota(self, user_id: str, target_date: Optional[date] = None) -> Dict[str, Any]:
        """
        Проверяет квоту пользователя.
        
        Args:
            user_id: ID пользователя
            target_date: Дата для проверки (если None, используется сегодня)
            
        Returns:
            {
                "remaining_minutes": float,
                "used_minutes": float,
                "limit_minutes": int,
                "is_premium": bool,
            }
        """
        if target_date is None:
            target_date = date.today()
        
        # Проверяем статус premium
        is_premium = self._is_premium(user_id)
        
        if is_premium:
            return {
                "remaining_minutes": float("inf"),
                "used_minutes": 0.0,
                "limit_minutes": float("inf"),
                "is_premium": True,
            }
        
        # Получаем использованные минуты за день
        used_minutes = self._get_used_minutes(user_id, target_date)
        remaining_minutes = max(0, self.free_minutes_per_day - used_minutes)
        
        return {
            "remaining_minutes": remaining_minutes,
            "used_minutes": used_minutes,
            "limit_minutes": self.free_minutes_per_day,
            "is_premium": False,
        }
    
    def can_record(self, user_id: str, duration_minutes: float = 0.0) -> bool:
        """
        Проверяет, может ли пользователь записать аудио.
        
        Args:
            user_id: ID пользователя
            duration_minutes: Длительность записи в минутах
            
        Returns:
            True если можно записать
        """
        quota = self.check_quota(user_id)
        
        if quota["is_premium"]:
            return True
        
        return quota["remaining_minutes"] >= duration_minutes
    
    def record_usage(self, user_id: str, duration_minutes: float, target_date: Optional[date] = None) -> bool:
        """
        Записывает использование минут.
        
        Args:
            user_id: ID пользователя
            duration_minutes: Использованные минуты
            target_date: Дата использования
            
        Returns:
            True если успешно
        """
        if target_date is None:
            target_date = date.today()
        
        try:
            # Сохраняем в БД (таблица usage_tracking)
            usage_data = {
                "user_id": user_id,
                "date": target_date.isoformat(),
                "duration_minutes": duration_minutes,
                "recorded_at": datetime.now().isoformat(),
            }
            
            # Пробуем обновить существующую запись или создать новую
            existing = self.db.select(
                "usage_tracking",
                filters={"user_id": user_id, "date": target_date.isoformat()},
                limit=1,
            )
            
            if existing:
                # Обновляем
                existing_record = existing[0]
                new_duration = existing_record.get("duration_minutes", 0) + duration_minutes
                self.db.update(
                    "usage_tracking",
                    id=existing_record["id"],
                    data={"duration_minutes": new_duration},
                )
            else:
                # Создаём новую запись
                self.db.insert("usage_tracking", usage_data)
            
            logger.info(
                "usage_recorded",
                user_id=user_id,
                duration_minutes=duration_minutes,
                date=target_date.isoformat(),
            )
            return True
            
        except Exception as e:
            logger.error("usage_recording_failed", error=str(e))
            return False
    
    def _is_premium(self, user_id: str) -> bool:
        """Проверяет, является ли пользователь premium."""
        try:
            # Проверяем в user_preferences или billing таблице
            preferences = self.db.select(
                "user_preferences",
                filters={"user_id": user_id},
                limit=1,
            )
            
            if preferences:
                return preferences[0].get("is_premium", False)
            
            return False
            
        except Exception as e:
            logger.warning("premium_check_failed", error=str(e))
            return False
    
    def _get_used_minutes(self, user_id: str, target_date: date) -> float:
        """Получает использованные минуты за день."""
        try:
            usage_records = self.db.select(
                "usage_tracking",
                filters={"user_id": user_id, "date": target_date.isoformat()},
                limit=1,
            )
            
            if usage_records:
                return float(usage_records[0].get("duration_minutes", 0.0))
            
            return 0.0
            
        except Exception as e:
            logger.warning("usage_retrieval_failed", error=str(e))
            return 0.0


def get_freemium_manager() -> FreemiumManager:
    """Фабричная функция для получения FreemiumManager."""
    return FreemiumManager()





