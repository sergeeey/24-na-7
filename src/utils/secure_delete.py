"""
Безопасное удаление файлов с перезаписью содержимого.

ПОЧЕМУ не просто unlink(): удаление inode не стирает данные с диска.
Для аудио с PII (голос = биометрия по KZ GDPR ст.20) нужна перезапись.
Одного прохода random достаточно для SSD (TRIM делает остальное)
и HDD (восстановление после random-перезаписи нереалистично).
"""
import os
from pathlib import Path
from typing import Union

try:
    from src.utils.logging import get_logger
    logger = get_logger("utils.secure_delete")
except Exception:
    import logging
    logger = logging.getLogger("utils.secure_delete")


def secure_delete(path: Union[str, Path]) -> bool:
    """
    Перезаписывает файл случайными данными, fsync, затем удаляет.

    Args:
        path: путь к файлу для удаления

    Returns:
        True если файл удалён, False если не существовал или ошибка
    """
    path = Path(path)
    if not path.exists():
        return False

    try:
        size = path.stat().st_size
        if size > 0:
            # ПОЧЕМУ os.urandom: криптографически случайные данные.
            # Один проход достаточен — DoD 5220.22-M требует 3, но для SSD
            # это бессмысленно (контроллер перемаппит блоки), а для HDD
            # одного random прохода достаточно по современным стандартам.
            with open(path, "r+b") as f:
                f.write(os.urandom(size))
                f.flush()
                os.fsync(f.fileno())

        path.unlink()
        logger.debug("secure_deleted", path=str(path), size=size)
        return True

    except PermissionError:
        logger.warning("secure_delete_permission_denied", path=str(path))
        # Fallback: обычное удаление лучше чем ничего
        try:
            path.unlink()
            return True
        except Exception:
            return False

    except Exception as e:
        logger.error("secure_delete_failed", path=str(path), error=str(e))
        # Fallback: попытка обычного удаления
        try:
            path.unlink()
            return True
        except Exception:
            return False
