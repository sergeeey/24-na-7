"""
Retention Policy — автоматическое удаление старых файлов.
Reflexio v2.1 — Surpass Smart Noter Sprint
"""
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict

from src.utils.logging import get_logger
from src.storage.audio_manager import get_audio_manager

logger = get_logger("storage.retention")


class RetentionPolicy:
    """Политика хранения данных."""
    
    def __init__(
        self,
        audio_retention_hours: int = 24,
        transcription_retention_days: int = 90,
        digest_retention_days: int = 365,
    ):
        """
        Args:
            audio_retention_hours: Время хранения аудио в часах (0 = без ограничений)
            transcription_retention_days: Время хранения транскрипций в днях
            digest_retention_days: Время хранения дайджестов в днях
        """
        self.audio_retention_hours = audio_retention_hours
        self.transcription_retention_days = transcription_retention_days
        self.digest_retention_days = digest_retention_days
        
        self.audio_manager = get_audio_manager()
    
    def cleanup_audio(self) -> int:
        """Очищает истёкшие аудио файлы."""
        if self.audio_retention_hours == 0:
            return 0
        
        return self.audio_manager.cleanup_expired()
    
    def cleanup_transcriptions(self) -> int:
        """Очищает старые транскрипции."""
        if self.transcription_retention_days == 0:
            return 0
        
        try:
            from src.storage.db import get_db
            db = get_db()
            
            cutoff_date = datetime.now() - timedelta(days=self.transcription_retention_days)
            
            # Удаляем старые транскрипции (если таблица существует)
            # Это зависит от структуры БД
            deleted_count = 0
            
            # Пример для SQLite
            if hasattr(db, "conn"):
                cursor = db.conn.cursor()
                cursor.execute(
                    "DELETE FROM transcriptions WHERE created_at < ?",
                    (cutoff_date.isoformat(),)
                )
                deleted_count = cursor.rowcount
                db.conn.commit()
            
            logger.info("transcriptions_cleaned", deleted_count=deleted_count)
            return deleted_count
            
        except Exception as e:
            logger.error("transcription_cleanup_failed", error=str(e))
            return 0
    
    def cleanup_digests(self) -> int:
        """Очищает старые дайджесты."""
        if self.digest_retention_days == 0:
            return 0
        
        try:
            digests_dir = Path("digests")
            if not digests_dir.exists():
                return 0
            
            cutoff_date = datetime.now() - timedelta(days=self.digest_retention_days)
            deleted_count = 0
            
            for digest_file in digests_dir.glob("digest_*.md"):
                try:
                    # Извлекаем дату из имени файла
                    date_str = digest_file.stem.replace("digest_", "")
                    file_date = datetime.strptime(date_str, "%Y-%m-%d").date()
                    
                    if file_date < cutoff_date.date():
                        digest_file.unlink()
                        # Удаляем соответствующий JSON и PDF если есть
                        json_file = digest_file.with_suffix(".json")
                        pdf_file = digest_file.with_suffix(".pdf")
                        if json_file.exists():
                            json_file.unlink()
                        if pdf_file.exists():
                            pdf_file.unlink()
                        
                        deleted_count += 1
                        
                except Exception as e:
                    logger.warning("digest_cleanup_file_failed", file=str(digest_file), error=str(e))
            
            logger.info("digests_cleaned", deleted_count=deleted_count)
            return deleted_count
            
        except Exception as e:
            logger.error("digest_cleanup_failed", error=str(e))
            return 0
    
    def cleanup_all(self) -> Dict[str, int]:
        """Выполняет полную очистку всех типов данных."""
        return {
            "audio": self.cleanup_audio(),
            "transcriptions": self.cleanup_transcriptions(),
            "digests": self.cleanup_digests(),
        }


def get_retention_policy() -> RetentionPolicy:
    """Фабричная функция для получения RetentionPolicy."""
    return RetentionPolicy()





