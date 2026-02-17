"""
Метрики монетизации и конверсии.
Reflexio v2.1 — Surpass Smart Noter Sprint
"""
from typing import Dict, Any, Optional
from datetime import date, datetime, timedelta
from pathlib import Path
import json

from src.utils.logging import get_logger
from src.storage.db import get_db

logger = get_logger("analytics.monetization")


class MonetizationAnalytics:
    """Аналитика монетизации."""
    
    def __init__(self):
        self.db = get_db()
        self.analytics_file = Path(".cache/monetization_analytics.json")
        self.analytics_file.parent.mkdir(parents=True, exist_ok=True)
    
    def track_conversion(self, user_id: str, from_plan: str, to_plan: str) -> bool:
        """
        Отслеживает конверсию пользователя.
        
        Args:
            user_id: ID пользователя
            from_plan: Исходный план (free/premium)
            to_plan: Целевой план (premium)
            
        Returns:
            True если успешно
        """
        try:
            conversion_data = {
                "user_id": user_id,
                "from_plan": from_plan,
                "to_plan": to_plan,
                "converted_at": datetime.now().isoformat(),
            }
            
            self.db.insert("conversions", conversion_data)
            
            logger.info("conversion_tracked", user_id=user_id, from_plan=from_plan, to_plan=to_plan)
            return True
            
        except Exception as e:
            logger.error("conversion_tracking_failed", error=str(e))
            return False
    
    def get_conversion_rate(
        self,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> Dict[str, Any]:
        """
        Вычисляет конверсию Free → Premium.
        
        Args:
            start_date: Начальная дата
            end_date: Конечная дата
            
        Returns:
            Метрики конверсии
        """
        try:
            if start_date is None:
                start_date = date.today() - timedelta(days=30)
            if end_date is None:
                end_date = date.today()
            
            # Получаем все конверсии за период
            conversions = self.db.select(
                "conversions",
                filters={
                    "from_plan": "free",
                    "to_plan": "premium",
                },
            )
            
            # Фильтруем по дате
            filtered_conversions = []
            for conv in conversions:
                converted_at = datetime.fromisoformat(conv["converted_at"]).date()
                if start_date <= converted_at <= end_date:
                    filtered_conversions.append(conv)
            
            # Получаем общее количество free пользователей
            free_users = self.db.select(
                "user_preferences",
                filters={"is_premium": False},
            )
            
            total_free = len(free_users)
            conversions_count = len(filtered_conversions)
            
            conversion_rate = (conversions_count / total_free * 100) if total_free > 0 else 0.0
            
            result = {
                "period": {
                    "start": start_date.isoformat(),
                    "end": end_date.isoformat(),
                },
                "total_free_users": total_free,
                "conversions": conversions_count,
                "conversion_rate": round(conversion_rate, 2),
                "target_rate": 5.0,
                "status": "meeting_target" if conversion_rate >= 5.0 else "below_target",
            }
            
            logger.info("conversion_rate_calculated", rate=conversion_rate)
            return result
            
        except Exception as e:
            logger.error("conversion_rate_calculation_failed", error=str(e))
            return {
                "conversion_rate": 0.0,
                "error": str(e),
            }
    
    def get_referral_activation_rate(
        self,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> Dict[str, Any]:
        """
        Вычисляет активацию referral системы.
        
        Args:
            start_date: Начальная дата
            end_date: Конечная дата
            
        Returns:
            Метрики referral активации
        """
        try:
            if start_date is None:
                start_date = date.today() - timedelta(days=30)
            if end_date is None:
                end_date = date.today()
            
            # Получаем все referral uses за период
            referral_uses = self.db.select("referral_uses")
            
            # Фильтруем по дате
            filtered_uses = []
            for use in referral_uses:
                used_at = datetime.fromisoformat(use["used_at"]).date()
                if start_date <= used_at <= end_date:
                    filtered_uses.append(use)
            
            # Получаем уникальных рефереров
            referrers = set(use["referrer_id"] for use in filtered_uses)
            
            # Получаем все referral коды
            all_referrals = self.db.select("referrals")
            total_referrals = len(all_referrals)
            
            activation_rate = (len(referrers) / total_referrals * 100) if total_referrals > 0 else 0.0
            
            result = {
                "period": {
                    "start": start_date.isoformat(),
                    "end": end_date.isoformat(),
                },
                "total_referrals": total_referrals,
                "active_referrers": len(referrers),
                "referral_uses": len(filtered_uses),
                "activation_rate": round(activation_rate, 2),
                "target_rate": 20.0,
                "status": "meeting_target" if activation_rate >= 20.0 else "below_target",
            }
            
            logger.info("referral_activation_rate_calculated", rate=activation_rate)
            return result
            
        except Exception as e:
            logger.error("referral_activation_rate_calculation_failed", error=str(e))
            return {
                "activation_rate": 0.0,
                "error": str(e),
            }
    
    def get_daily_metrics(self, target_date: Optional[date] = None) -> Dict[str, Any]:
        """
        Получает ежедневные метрики монетизации.
        
        Args:
            target_date: Дата (если None, используется сегодня)
            
        Returns:
            Ежедневные метрики
        """
        if target_date is None:
            target_date = date.today()
        
        conversion_rate = self.get_conversion_rate(target_date, target_date)
        referral_rate = self.get_referral_activation_rate(target_date, target_date)
        
        return {
            "date": target_date.isoformat(),
            "conversion": conversion_rate,
            "referral": referral_rate,
        }
    
    def save_analytics(self, metrics: Dict[str, Any]):
        """Сохраняет аналитику в файл."""
        try:
            # Загружаем существующие данные
            if self.analytics_file.exists():
                data = json.loads(self.analytics_file.read_text(encoding="utf-8"))
            else:
                data = {"metrics": []}
            
            # Добавляем новые метрики
            data["metrics"].append(metrics)
            # Ограничиваем историю (последние 90 дней)
            data["metrics"] = data["metrics"][-90:]
            
            # Сохраняем
            self.analytics_file.write_text(
                json.dumps(data, indent=2, ensure_ascii=False),
                encoding="utf-8"
            )
            
        except Exception as e:
            logger.error("analytics_save_failed", error=str(e))


def get_monetization_analytics() -> MonetizationAnalytics:
    """Фабричная функция для получения MonetizationAnalytics."""
    return MonetizationAnalytics()





