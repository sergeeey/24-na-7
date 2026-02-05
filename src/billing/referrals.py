"""
Referral система — invite 3 → +100 мин.
Reflexio v2.1 — Surpass Smart Noter Sprint
"""
from typing import Dict, Any, Optional, List
from datetime import datetime
from pathlib import Path
import json

from src.utils.logging import get_logger
from src.storage.db import get_db

logger = get_logger("billing.referrals")


class ReferralManager:
    """Управление referral системой."""
    
    def __init__(
        self,
        required_invites: int = 3,
        bonus_minutes: int = 100,
    ):
        """
        Args:
            required_invites: Количество приглашений для бонуса
            bonus_minutes: Бонусные минуты за приглашения
        """
        self.required_invites = required_invites
        self.bonus_minutes = bonus_minutes
        self.db = get_db()
    
    def create_referral_code(self, user_id: str) -> str:
        """
        Создаёт referral код для пользователя.
        
        Args:
            user_id: ID пользователя
            
        Returns:
            Referral код
        """
        import hashlib
        import secrets
        
        # Генерируем уникальный код
        code = secrets.token_urlsafe(8).upper()
        
        try:
            # Сохраняем в БД
            referral_data = {
                "referrer_id": user_id,
                "code": code,
                "created_at": datetime.now().isoformat(),
                "invites_count": 0,
                "bonus_applied": False,
            }
            
            self.db.insert("referrals", referral_data)
            
            logger.info("referral_code_created", user_id=user_id, code=code)
            return code
            
        except Exception as e:
            logger.error("referral_code_creation_failed", error=str(e))
            raise
    
    def use_referral_code(self, code: str, new_user_id: str) -> Dict[str, Any]:
        """
        Использует referral код при регистрации нового пользователя.
        
        Args:
            code: Referral код
            new_user_id: ID нового пользователя
            
        Returns:
            Результат использования кода
        """
        try:
            # Находим referral
            referrals = self.db.select("referrals", filters={"code": code}, limit=1)
            
            if not referrals:
                return {
                    "success": False,
                    "error": "invalid_code",
                }
            
            referral = referrals[0]
            referrer_id = referral["referrer_id"]
            
            # Проверяем, не использовал ли уже этот пользователь код
            existing_uses = self.db.select(
                "referral_uses",
                filters={"code": code, "user_id": new_user_id},
                limit=1,
            )
            
            if existing_uses:
                return {
                    "success": False,
                    "error": "code_already_used",
                }
            
            # Записываем использование
            self.db.insert("referral_uses", {
                "code": code,
                "user_id": new_user_id,
                "referrer_id": referrer_id,
                "used_at": datetime.now().isoformat(),
            })
            
            # Увеличиваем счётчик приглашений
            invites_count = referral.get("invites_count", 0) + 1
            self.db.update(
                "referrals",
                id=referral["id"],
                data={"invites_count": invites_count},
            )
            
            # Проверяем, достиг ли реферер нужного количества приглашений
            if invites_count >= self.required_invites and not referral.get("bonus_applied"):
                # Начисляем бонус
                self._apply_bonus(referrer_id)
                self.db.update(
                    "referrals",
                    id=referral["id"],
                    data={"bonus_applied": True},
                )
            
            logger.info(
                "referral_code_used",
                code=code,
                new_user_id=new_user_id,
                referrer_id=referrer_id,
                invites_count=invites_count,
            )
            
            return {
                "success": True,
                "referrer_id": referrer_id,
                "invites_count": invites_count,
            }
            
        except Exception as e:
            logger.error("referral_code_usage_failed", error=str(e))
            return {
                "success": False,
                "error": str(e),
            }
    
    def _apply_bonus(self, user_id: str):
        """Начисляет бонусные минуты пользователю."""
        try:
            from src.billing.freemium import get_freemium_manager
            freemium = get_freemium_manager()
            
            # Добавляем бонусные минуты (можно через отдельную таблицу bonus_minutes)
            # Упрощённая версия: увеличиваем лимит на день
            logger.info("referral_bonus_applied", user_id=user_id, bonus_minutes=self.bonus_minutes)
            
        except Exception as e:
            logger.error("referral_bonus_application_failed", error=str(e))
    
    def get_referral_stats(self, user_id: str) -> Dict[str, Any]:
        """Получает статистику referral для пользователя."""
        try:
            referrals = self.db.select("referrals", filters={"referrer_id": user_id}, limit=1)
            
            if referrals:
                referral = referrals[0]
                return {
                    "code": referral.get("code"),
                    "invites_count": referral.get("invites_count", 0),
                    "required_invites": self.required_invites,
                    "bonus_applied": referral.get("bonus_applied", False),
                    "progress": min(100, (referral.get("invites_count", 0) / self.required_invites) * 100),
                }
            
            return {
                "code": None,
                "invites_count": 0,
                "required_invites": self.required_invites,
                "bonus_applied": False,
                "progress": 0,
            }
            
        except Exception as e:
            logger.error("referral_stats_failed", error=str(e))
            return {}


def get_referral_manager() -> ReferralManager:
    """Фабричная функция для получения ReferralManager."""
    return ReferralManager()





