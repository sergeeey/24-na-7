"""
Telegram sender для отправки дайджестов.
Reflexio v2.1 — Surpass Smart Noter Sprint
"""
import os
from pathlib import Path
from datetime import date
from typing import Optional

from src.utils.logging import get_logger

logger = get_logger("digest.telegram")

try:
    from telegram import Bot
    from telegram.error import TelegramError
    TELEGRAM_AVAILABLE = True
except ImportError:
    TELEGRAM_AVAILABLE = False
    logger.warning("python-telegram-bot not available. Install: pip install python-telegram-bot")


class TelegramDigestSender:
    """Отправляет дайджесты в Telegram."""
    
    def __init__(
        self,
        bot_token: Optional[str] = None,
        chat_id: Optional[str] = None,
    ):
        """
        Args:
            bot_token: Telegram Bot Token (или из TELEGRAM_BOT_TOKEN env)
            chat_id: Chat ID для отправки (или из TELEGRAM_CHAT_ID env)
        """
        if not TELEGRAM_AVAILABLE:
            raise ImportError("python-telegram-bot package required. Install: pip install python-telegram-bot")
        
        self.bot_token = bot_token or os.getenv("TELEGRAM_BOT_TOKEN")
        self.chat_id = chat_id or os.getenv("TELEGRAM_CHAT_ID")
        
        if not self.bot_token:
            raise ValueError("TELEGRAM_BOT_TOKEN not set")
        if not self.chat_id:
            raise ValueError("TELEGRAM_CHAT_ID not set")
        
        self.bot = Bot(token=self.bot_token)
        logger.info("telegram_sender_initialized", chat_id=self.chat_id)
    
    def send_digest(
        self,
        target_date: date,
        markdown_file: Path,
        pdf_file: Optional[Path] = None,
    ) -> bool:
        """
        Отправляет дайджест в Telegram.
        
        Args:
            target_date: Дата дайджеста
            markdown_file: Путь к markdown файлу
            pdf_file: Путь к PDF файлу (опционально)
            
        Returns:
            True если успешно отправлено
        """
        try:
            # Читаем markdown
            markdown_content = markdown_file.read_text(encoding="utf-8")
            
            # Ограничиваем длину сообщения (Telegram лимит 4096 символов)
            if len(markdown_content) > 4000:
                markdown_content = markdown_content[:4000] + "\n\n... (полный дайджест в PDF)"
            
            # Формируем сообщение
            message = f"📊 <b>Reflexio Digest — {target_date.strftime('%d %B %Y')}</b>\n\n"
            message += markdown_content.replace("*", "").replace("#", "")  # Упрощаем markdown для Telegram
            
            # Отправляем текстовое сообщение
            self.bot.send_message(
                chat_id=self.chat_id,
                text=message,
                parse_mode="HTML",
            )
            
            logger.info("telegram_message_sent", date=target_date.isoformat())
            
            # Отправляем PDF если есть
            if pdf_file and pdf_file.exists():
                with open(pdf_file, "rb") as pdf:
                    self.bot.send_document(
                        chat_id=self.chat_id,
                        document=pdf,
                        filename=f"digest_{target_date.isoformat()}.pdf",
                        caption=f"📄 Полный дайджест за {target_date.strftime('%d %B %Y')}",
                    )
                
                logger.info("telegram_pdf_sent", date=target_date.isoformat())
            
            return True
            
        except TelegramError as e:
            logger.error("telegram_send_error", error=str(e))
            return False
        except Exception as e:
            logger.error("telegram_send_failed", error=str(e))
            return False
    
    def send_text(self, text: str) -> bool:
        """Отправляет текстовое сообщение."""
        try:
            self.bot.send_message(
                chat_id=self.chat_id,
                text=text,
            )
            return True
        except Exception as e:
            logger.error("telegram_text_send_failed", error=str(e))
            return False





