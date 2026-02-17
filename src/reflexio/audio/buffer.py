"""
Буфер аудио-кадров для накопления сегментов речи.
Интеграция из Golos: буфер с фиксированной длительностью кадра.
"""
from typing import List


class AudioBuffer:
    """Буфер для накопления PCM-кадров перед сохранением сегмента."""

    def __init__(self) -> None:
        self._frames: List[bytes] = []

    def append(self, frame: bytes) -> None:
        """Добавляет кадр в буфер."""
        self._frames.append(frame)

    def extend(self, frames: List[bytes]) -> None:
        """Добавляет несколько кадров."""
        self._frames.extend(frames)

    def clear(self) -> None:
        """Очищает буфер."""
        self._frames.clear()

    def get_data(self) -> bytes:
        """Возвращает все данные буфера как один блок байт."""
        return b"".join(self._frames)

    def is_empty(self) -> bool:
        """Проверяет, пуст ли буфер."""
        return len(self._frames) == 0

    def __len__(self) -> int:
        return len(self._frames)
