"""
Менеджер аудио файлов с шифрованием и retention policy.
Reflexio v2.1 — Surpass Smart Noter Sprint
"""
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
import json

from src.utils.logging import get_logger
from src.utils.config import settings
from src.storage.encryption import get_audio_encryption

logger = get_logger("storage.audio")


class AudioManager:
    """Управление аудио файлами с шифрованием и retention policy."""
    
    def __init__(
        self,
        storage_path: Optional[Path] = None,
        encrypt: bool = True,
        retention_hours: int = 24,
    ):
        """
        Args:
            storage_path: Путь к хранилищу аудио
            encrypt: Шифровать ли файлы
            retention_hours: Время хранения в часах (0 = без ограничений)
        """
        if storage_path is None:
            storage_path = settings.STORAGE_PATH / "audio"
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        
        self.encrypt = encrypt
        self.retention_hours = retention_hours
        
        self.encryption = None
        if encrypt:
            self.encryption = get_audio_encryption()
            if not self.encryption:
                logger.warning("encryption_not_available", fallback="unencrypted")
                self.encrypt = False
    
    def store_audio(
        self,
        audio_path: Path,
        metadata: Optional[Dict[str, Any]] = None,
        user_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Сохраняет аудио файл с шифрованием.
        
        Args:
            audio_path: Путь к исходному файлу
            metadata: Метаданные файла
            user_id: ID пользователя (для tenant_id)
            
        Returns:
            Информация о сохранённом файле
        """
        try:
            # Генерируем уникальное имя файла
            file_id = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{audio_path.stem}"
            stored_path = self.storage_path / file_id
            
            # Копируем файл
            import shutil
            shutil.copy2(audio_path, stored_path)
            
            # Шифруем если нужно
            if self.encrypt and self.encryption:
                encrypted_path = self.encryption.encrypt_file(stored_path)
                # Удаляем незашифрованную версию
                stored_path.unlink()
                stored_path = encrypted_path
                logger.info("audio_encrypted", file_id=file_id)
            
            # Сохраняем метаданные
            metadata_file = self.storage_path / f"{file_id}.meta.json"
            metadata_data = {
                "file_id": file_id,
                "original_filename": audio_path.name,
                "stored_path": str(stored_path),
                "encrypted": self.encrypt,
                "user_id": user_id,
                "stored_at": datetime.now().isoformat(),
                "retention_hours": self.retention_hours,
                "expires_at": (datetime.now() + timedelta(hours=self.retention_hours)).isoformat() if self.retention_hours > 0 else None,
                **(metadata or {}),
            }
            metadata_file.write_text(
                json.dumps(metadata_data, indent=2, ensure_ascii=False),
                encoding="utf-8"
            )
            
            logger.info(
                "audio_stored",
                file_id=file_id,
                encrypted=self.encrypt,
                retention_hours=self.retention_hours,
            )
            
            return metadata_data
            
        except Exception as e:
            logger.error("audio_storage_failed", error=str(e))
            raise
    
    def get_audio(self, file_id: str, decrypt: bool = True) -> Optional[Path]:
        """
        Получает аудио файл (расшифровывает если нужно).
        
        Args:
            file_id: ID файла
            decrypt: Расшифровывать ли файл
            
        Returns:
            Путь к файлу или None
        """
        try:
            # Ищем файл
            metadata_file = self.storage_path / f"{file_id}.meta.json"
            if not metadata_file.exists():
                logger.warning("audio_metadata_not_found", file_id=file_id)
                return None
            
            metadata = json.loads(metadata_file.read_text(encoding="utf-8"))
            stored_path = Path(metadata["stored_path"])
            
            if not stored_path.exists():
                logger.warning("audio_file_not_found", file_id=file_id, path=str(stored_path))
                return None
            
            # Проверяем retention
            if metadata.get("expires_at"):
                expires_at = datetime.fromisoformat(metadata["expires_at"])
                if datetime.now() > expires_at:
                    logger.warning("audio_expired", file_id=file_id, expires_at=metadata["expires_at"])
                    # Файл истёк, но возвращаем его (удаление через cleanup)
            
            # Расшифровываем если нужно
            if decrypt and metadata.get("encrypted") and self.encryption:
                temp_path = self.storage_path / f"{file_id}.decrypted"
                decrypted_path = self.encryption.decrypt_file(stored_path, temp_path)
                return decrypted_path
            
            return stored_path
            
        except Exception as e:
            logger.error("audio_retrieval_failed", error=str(e))
            return None
    
    def cleanup_expired(self) -> int:
        """
        Удаляет истёкшие файлы (zero-retention).
        
        Returns:
            Количество удалённых файлов
        """
        if self.retention_hours == 0:
            return 0
        
        deleted_count = 0
        cutoff_time = datetime.now() - timedelta(hours=self.retention_hours)
        
        try:
            for metadata_file in self.storage_path.glob("*.meta.json"):
                try:
                    metadata = json.loads(metadata_file.read_text(encoding="utf-8"))
                    stored_at = datetime.fromisoformat(metadata["stored_at"])
                    
                    if stored_at < cutoff_time:
                        # Удаляем файл и метаданные
                        stored_path = Path(metadata["stored_path"])
                        if stored_path.exists():
                            stored_path.unlink()
                        
                        metadata_file.unlink()
                        deleted_count += 1
                        
                        logger.info("expired_audio_deleted", file_id=metadata.get("file_id"))
                        
                except Exception as e:
                    logger.warning("cleanup_file_failed", file=str(metadata_file), error=str(e))
            
            logger.info("cleanup_completed", deleted_count=deleted_count)
            return deleted_count
            
        except Exception as e:
            logger.error("cleanup_failed", error=str(e))
            return deleted_count
    
    def get_stats(self) -> Dict[str, Any]:
        """Возвращает статистику хранилища."""
        total_files = len(list(self.storage_path.glob("*.meta.json")))
        total_size = sum(f.stat().st_size for f in self.storage_path.glob("*") if f.is_file() and not f.name.endswith(".meta.json"))
        
        return {
            "total_files": total_files,
            "total_size_bytes": total_size,
            "total_size_mb": round(total_size / (1024 * 1024), 2),
            "encryption_enabled": self.encrypt,
            "retention_hours": self.retention_hours,
        }


def get_audio_manager() -> AudioManager:
    """Фабричная функция для получения AudioManager."""
    return AudioManager()

