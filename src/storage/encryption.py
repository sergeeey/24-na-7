"""
Локальное AES-шифрование для аудио файлов.
Reflexio v2.1 — Surpass Smart Noter Sprint
"""
from pathlib import Path
from typing import Optional
import os
import base64

from src.utils.logging import get_logger

logger = get_logger("storage.encryption")

try:
    from cryptography.fernet import Fernet
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    CRYPTOGRAPHY_AVAILABLE = True
except ImportError:
    CRYPTOGRAPHY_AVAILABLE = False
    logger.warning("cryptography not available. Install: pip install cryptography")


class AudioEncryption:
    """Шифрование аудио файлов через AES."""
    
    def __init__(self, key: Optional[bytes] = None):
        """
        Инициализация шифрования.
        
        Args:
            key: Ключ шифрования (если None, генерируется из пароля)
        """
        if not CRYPTOGRAPHY_AVAILABLE:
            raise ImportError("cryptography package required. Install: pip install cryptography")
        
        if key is None:
            # Генерируем ключ из пароля (или используем из окружения)
            password = os.getenv("AUDIO_ENCRYPTION_PASSWORD", "reflexio-default-key").encode()
            salt = os.getenv("AUDIO_ENCRYPTION_SALT", "reflexio-salt").encode()
            
            kdf = PBKDF2HMAC(
                algorithm=hashes.SHA256(),
                length=32,
                salt=salt,
                iterations=100000,
            )
            key = base64.urlsafe_b64encode(kdf.derive(password))
        
        self.cipher = Fernet(key)
        logger.info("audio_encryption_initialized")
    
    def encrypt_file(self, input_path: Path, output_path: Optional[Path] = None) -> Path:
        """
        Шифрует аудио файл.
        
        Args:
            input_path: Путь к исходному файлу
            output_path: Путь для зашифрованного файла (если None, добавляется .enc)
            
        Returns:
            Путь к зашифрованному файлу
        """
        if output_path is None:
            output_path = input_path.with_suffix(input_path.suffix + ".enc")
        
        try:
            # Читаем исходный файл
            with open(input_path, "rb") as f:
                plaintext = f.read()
            
            # Шифруем
            encrypted = self.cipher.encrypt(plaintext)
            
            # Сохраняем зашифрованный файл
            with open(output_path, "wb") as f:
                f.write(encrypted)
            
            logger.info("file_encrypted", input_path=str(input_path), output_path=str(output_path))
            return output_path
            
        except Exception as e:
            logger.error("encryption_failed", error=str(e))
            raise
    
    def decrypt_file(self, input_path: Path, output_path: Optional[Path] = None) -> Path:
        """
        Расшифровывает аудио файл.
        
        Args:
            input_path: Путь к зашифрованному файлу
            output_path: Путь для расшифрованного файла (если None, убирается .enc)
            
        Returns:
            Путь к расшифрованному файлу
        """
        if output_path is None:
            if input_path.suffix == ".enc":
                output_path = input_path.with_suffix("")
            else:
                output_path = input_path.with_suffix(".dec" + input_path.suffix)
        
        try:
            # Читаем зашифрованный файл
            with open(input_path, "rb") as f:
                encrypted = f.read()
            
            # Расшифровываем
            plaintext = self.cipher.decrypt(encrypted)
            
            # Сохраняем расшифрованный файл
            with open(output_path, "wb") as f:
                f.write(plaintext)
            
            logger.info("file_decrypted", input_path=str(input_path), output_path=str(output_path))
            return output_path
            
        except Exception as e:
            logger.error("decryption_failed", error=str(e))
            raise
    
    def encrypt_bytes(self, data: bytes) -> bytes:
        """Шифрует байты."""
        return self.cipher.encrypt(data)
    
    def decrypt_bytes(self, encrypted_data: bytes) -> bytes:
        """Расшифровывает байты."""
        return self.cipher.decrypt(encrypted_data)


def get_audio_encryption() -> Optional[AudioEncryption]:
    """Фабричная функция для получения AudioEncryption."""
    if not CRYPTOGRAPHY_AVAILABLE:
        logger.warning("encryption_not_available", reason="cryptography_not_installed")
        return None
    
    try:
        return AudioEncryption()
    except Exception as e:
        logger.error("encryption_initialization_failed", error=str(e))
        return None





