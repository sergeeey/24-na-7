"""
Stripe интеграция для IAP (In-App Purchases).
Reflexio v2.1 — Surpass Smart Noter Sprint
"""
import os
from typing import Dict, Any, Optional
from datetime import datetime, timedelta

from src.utils.logging import get_logger

logger = get_logger("billing.stripe")

try:
    import stripe
    STRIPE_AVAILABLE = True
except ImportError:
    STRIPE_AVAILABLE = False
    logger.warning("stripe not available. Install: pip install stripe")


class StripeIntegration:
    """Интеграция со Stripe для платежей."""
    
    def __init__(self, api_key: Optional[str] = None):
        """
        Args:
            api_key: Stripe API ключ (если None, берётся из окружения)
        """
        if not STRIPE_AVAILABLE:
            raise ImportError("stripe package required. Install: pip install stripe")
        
        self.api_key = api_key or os.getenv("STRIPE_SECRET_KEY")
        if not self.api_key:
            raise ValueError("STRIPE_SECRET_KEY not set")
        
        stripe.api_key = self.api_key
        self.client = stripe
        logger.info("stripe_integration_initialized")
    
    def create_checkout_session(
        self,
        user_id: str,
        price_id: str,
        success_url: str,
        cancel_url: str,
    ) -> Dict[str, Any]:
        """
        Создаёт сессию оплаты.
        
        Args:
            user_id: ID пользователя
            price_id: Stripe Price ID
            success_url: URL для успешной оплаты
            cancel_url: URL для отмены
            
        Returns:
            Информация о сессии
        """
        try:
            session = self.client.checkout.Session.create(
                customer_email=None,  # Можно добавить email пользователя
                payment_method_types=["card"],
                line_items=[{
                    "price": price_id,
                    "quantity": 1,
                }],
                mode="subscription",
                success_url=success_url,
                cancel_url=cancel_url,
                metadata={
                    "user_id": user_id,
                },
            )
            
            logger.info("checkout_session_created", session_id=session.id, user_id=user_id)
            
            return {
                "session_id": session.id,
                "url": session.url,
                "status": session.status,
            }
            
        except Exception as e:
            logger.error("checkout_session_creation_failed", error=str(e))
            raise
    
    def handle_webhook(self, payload: bytes, signature: str) -> Dict[str, Any]:
        """
        Обрабатывает webhook от Stripe.
        
        Args:
            payload: Тело запроса
            signature: Подпись Stripe
            
        Returns:
            Результат обработки
        """
        try:
            webhook_secret = os.getenv("STRIPE_WEBHOOK_SECRET")
            if not webhook_secret:
                raise ValueError("STRIPE_WEBHOOK_SECRET not set")
            
            event = self.client.Webhook.construct_event(
                payload, signature, webhook_secret
            )
            
            # Обрабатываем события
            if event["type"] == "checkout.session.completed":
                session = event["data"]["object"]
                user_id = session["metadata"].get("user_id")
                
                if user_id:
                    # Активируем premium для пользователя
                    self._activate_premium(user_id, days=30)  # 30 дней premium
                    logger.info("premium_activated", user_id=user_id)
            
            return {"status": "success", "event_type": event["type"]}
            
        except Exception as e:
            logger.error("webhook_handling_failed", error=str(e))
            raise
    
    def _activate_premium(self, user_id: str, days: int = 30):
        """Активирует premium подписку для пользователя."""
        try:
            from src.storage.db import get_db
            db = get_db()
            
            expires_at = datetime.now() + timedelta(days=days)
            
            # Обновляем user_preferences
            preferences = db.select("user_preferences", filters={"user_id": user_id}, limit=1)
            
            if preferences:
                db.update(
                    "user_preferences",
                    id=preferences[0]["id"],
                    data={
                        "is_premium": True,
                        "premium_expires_at": expires_at.isoformat(),
                    },
                )
            else:
                db.insert("user_preferences", {
                    "user_id": user_id,
                    "is_premium": True,
                    "premium_expires_at": expires_at.isoformat(),
                })
            
            logger.info("premium_activated_db", user_id=user_id, expires_at=expires_at.isoformat())
            
        except Exception as e:
            logger.error("premium_activation_failed", error=str(e))
            raise


def get_stripe_integration() -> Optional[StripeIntegration]:
    """Фабричная функция для получения StripeIntegration."""
    if not STRIPE_AVAILABLE:
        return None
    
    try:
        return StripeIntegration()
    except Exception as e:
        logger.error("stripe_integration_failed", error=str(e))
        return None





