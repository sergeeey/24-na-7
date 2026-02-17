"""Process Locking — предотвращение параллельного запуска.

Использование:
    from src.utils.process_lock import ProcessLock

    with ProcessLock("daily_digest"):
        # Critical section — только один process
        generate_digest()
"""
import os
import sys
import time
import atexit
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class ProcessLockError(Exception):
    """Ошибка при получении lock."""
    pass


class ProcessLock:
    """Process-level lock через PID file.

    Attributes:
        name: Имя lock (например, "daily_digest")
        lock_dir: Директория для PID files
        timeout: Timeout для получения lock (секунды)
        pid_file: Путь к PID file
        locked: Флаг успешного locking
    """

    def __init__(
        self,
        name: str,
        lock_dir: Optional[Path] = None,
        timeout: int = 60,
    ):
        """Инициализация ProcessLock.

        Args:
            name: Имя lock
            lock_dir: Директория для PID files (default: /tmp или TEMP)
            timeout: Timeout для получения lock (0 = no wait)
        """
        self.name = name
        self.timeout = timeout
        self.locked = False

        # Определяем lock directory
        if lock_dir is None:
            if os.name == "nt":  # Windows
                lock_dir = Path(os.environ.get("TEMP", "C:\\Temp"))
            else:  # Unix/Linux
                lock_dir = Path("/tmp")

        self.lock_dir = lock_dir
        self.lock_dir.mkdir(parents=True, exist_ok=True)

        # PID file path
        self.pid_file = self.lock_dir / f"{self.name}.pid"

        # Register cleanup on exit
        atexit.register(self._cleanup)

    def acquire(self) -> bool:
        """Получить lock.

        Returns:
            True если lock получен, False если timeout

        Raises:
            ProcessLockError: Если не удалось получить lock после timeout
        """
        start_time = time.time()

        while True:
            if self._try_acquire():
                self.locked = True
                logger.info(
                    f"process_lock_acquired: name={self.name}, pid={os.getpid()}, pid_file={self.pid_file}"
                )
                return True

            elapsed = time.time() - start_time
            if elapsed >= self.timeout:
                # Проверяем, не устарел ли lock (stale lock detection)
                if self._is_stale_lock():
                    logger.warning(
                        f"stale_lock_detected: name={self.name}, removing_stale=True"
                    )
                    self._force_remove()
                    # Retry после удаления stale lock
                    if self._try_acquire():
                        self.locked = True
                        return True

                raise ProcessLockError(
                    f"Could not acquire lock '{self.name}' after {self.timeout}s"
                )

            time.sleep(1)

    def _try_acquire(self) -> bool:
        """Попытка получить lock (non-blocking).

        Returns:
            True если lock получен
        """
        try:
            # Try to create PID file exclusively (fails if exists)
            with open(self.pid_file, "x") as f:
                f.write(str(os.getpid()))
            return True

        except FileExistsError:
            # Lock уже существует
            return False

        except Exception as e:
            logger.error(f"process_lock_error: name={self.name}, error={e}")
            return False

    def _is_stale_lock(self) -> bool:
        """Проверяет, не устарел ли lock (process завершился).

        Returns:
            True если lock stale (process не существует)
        """
        if not self.pid_file.exists():
            return False

        try:
            # Read PID from lock file
            with open(self.pid_file, "r") as f:
                pid = int(f.read().strip())

            # Check if process exists
            if os.name == "nt":  # Windows
                import psutil
                return not psutil.pid_exists(pid)
            else:  # Unix/Linux
                try:
                    # Send signal 0 (no-op, just check if process exists)
                    os.kill(pid, 0)
                    return False  # Process exists
                except OSError:
                    return True  # Process does not exist

        except (ValueError, FileNotFoundError):
            # Invalid PID file → stale
            return True

        except Exception as e:
            logger.warning(f"stale_lock_check_failed: name={self.name}, error={e}")
            return False  # Assume not stale if can't determine

    def release(self):
        """Освобождает lock."""
        if not self.locked:
            return

        self._cleanup()
        self.locked = False

        logger.info(f"process_lock_released: name={self.name}, pid={os.getpid()}")

    def _cleanup(self):
        """Удаляет PID file."""
        try:
            if self.pid_file.exists():
                self.pid_file.unlink()
        except Exception as e:
            logger.error(f"process_lock_cleanup_failed: name={self.name}, error={e}")

    def _force_remove(self):
        """Принудительно удаляет lock (для stale locks)."""
        try:
            if self.pid_file.exists():
                self.pid_file.unlink()
                logger.info(f"stale_lock_removed: name={self.name}, pid_file={self.pid_file}")
        except Exception as e:
            logger.error(f"force_remove_failed: name={self.name}, error={e}")

    def __enter__(self):
        """Context manager entry."""
        self.acquire()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.release()

    def __del__(self):
        """Cleanup on garbage collection."""
        self._cleanup()


__all__ = ["ProcessLock", "ProcessLockError"]
