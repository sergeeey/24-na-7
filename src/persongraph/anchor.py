"""
Name-Voice Anchor — автоматическая привязка имени к голосу.

Принцип:
  Когда пользователь обращается по имени к собеседнику непосредственно
  перед сменой спикера, следующий голосовой сегмент — кандидат на
  владельца этого имени.

  Пример:
    [0.0–4.0] Пользователь: "Максим, как думаешь по поводу релиза?"
    [4.0–9.0] Другой голос: "Я считаю нужно перенести..."
    → NameAnchor(name="Максим", speaker="SPEAKER_1", confidence=0.6)

  Каждое повторное подтверждение поднимает confidence на 0.05.
  При confidence ≥ 0.85 AND count ≥ 10 — профиль готов к подтверждению.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from src.utils.logging import get_logger

logger = get_logger("persongraph.anchor")

# ──────────────────────────────────────────────
# Типы данных
# ──────────────────────────────────────────────

@dataclass
class DiarizedSegment:
    """Сегмент аудио с меткой спикера (выход диаризатора)."""
    speaker: str        # "SPEAKER_0", "SPEAKER_1", ...
    start: float        # секунды
    end: float          # секунды

    @property
    def duration(self) -> float:
        return self.end - self.start


@dataclass
class WordWithTimestamp:
    """Слово с временной меткой из ASR (Whisper word timestamps)."""
    word: str
    start: float
    end: float


@dataclass
class NameAnchor:
    """
    Привязка имени к голосовому сегменту.

    Attributes:
        name:          Имя из обращения ("Максим")
        speaker_label: Временная метка спикера ("SPEAKER_1")
        segment:       Аудио-сегмент кандидата
        confidence:    Уверенность 0.0–1.0 (растёт при подтверждениях)
        ingest_id:     ID записи-источника
    """
    name: str
    speaker_label: str
    segment: DiarizedSegment
    confidence: float = 0.6
    ingest_id: str = ""


# ──────────────────────────────────────────────
# Паттерны звательного обращения
# ──────────────────────────────────────────────

# Русские имена в им. падеже — первая буква заглавная, 2+ символа.
# Фильтруем вводные слова, которые выглядят как имена но не являются ими.
_NON_NAMES: frozenset[str] = frozenset({
    "все", "вот", "нет", "да", "ну", "так", "эй", "ой", "ах",
    "хорошо", "ладно", "понятно", "отлично", "конечно", "привет",
})

# Паттерн 1: "Максим," — имя перед запятой в конце реплики пользователя
_PAT_TRAILING_COMMA = re.compile(
    r"\b([А-ЯЁ][а-яё]{1,19}),\s*$",
    re.UNICODE,
)

# Паттерн 2: "Максим, как / что / ты / вы / давай / скажи..."
_PAT_VOCATIVE_CLAUSE = re.compile(
    r"\b([А-ЯЁ][а-яё]{1,19}),\s+(?:как|что|ты|вы|давай|скажи|расскажи|объясни|смотри|слушай|помни|знаешь)",
    re.UNICODE | re.IGNORECASE,
)

# Паттерн 3: "Эй, Максим" / "Слушай, Максим"
_PAT_HEY_NAME = re.compile(
    r"(?:эй|слушай|послушай|стоп|подожди)[,\s]+([А-ЯЁ][а-яё]{1,19})\b",
    re.UNICODE | re.IGNORECASE,
)


def _extract_vocative_name(text: str) -> Optional[str]:
    """
    Извлекает имя в звательном обращении из текста.
    Возвращает None если имя не найдено или слово из стоп-листа.
    """
    for pattern in (_PAT_TRAILING_COMMA, _PAT_VOCATIVE_CLAUSE, _PAT_HEY_NAME):
        m = pattern.search(text)
        if m:
            name = m.group(1).strip()
            if name.lower() not in _NON_NAMES and len(name) >= 2:
                return name
    return None


def _words_in_segment(
    words: list[WordWithTimestamp],
    segment: DiarizedSegment,
    tolerance: float = 0.1,
) -> list[WordWithTimestamp]:
    """Фильтрует слова, попадающие в временной диапазон сегмента."""
    return [
        w for w in words
        if w.start >= (segment.start - tolerance)
        and w.end <= (segment.end + tolerance)
    ]


# ──────────────────────────────────────────────
# Основной экстрактор
# ──────────────────────────────────────────────

# Максимальный зазор между концом реплики пользователя
# и началом реплики кандидата (секунды).
_MAX_GAP_SEC: float = 3.0


class NameAnchorExtractor:
    """
    Извлекает name-voice якоря из результатов диаризации + ASR.

    Использование:
        extractor = NameAnchorExtractor(user_speaker="SPEAKER_0")
        anchors = extractor.extract(segments, words, ingest_id="abc-123")
    """

    def __init__(self, user_speaker: str = "SPEAKER_0"):
        self.user_speaker = user_speaker

    def extract(
        self,
        segments: list[DiarizedSegment],
        words: list[WordWithTimestamp],
        ingest_id: str = "",
    ) -> list[NameAnchor]:
        """
        Основной метод: проходит по сегментам, ищет якоря.

        Args:
            segments:   Список сегментов с метками спикеров
            words:      Слова с временными метками из ASR
            ingest_id:  ID источника (для трассировки)

        Returns:
            Список NameAnchor — привязок имя → голосовой сегмент
        """
        anchors: list[NameAnchor] = []

        for i, seg in enumerate(segments[:-1]):
            # Интересуют только реплики пользователя
            if seg.speaker != self.user_speaker:
                continue

            # Слова в этой реплике пользователя
            seg_words = _words_in_segment(words, seg)
            if not seg_words:
                continue

            # Собираем текст реплики
            text = " ".join(w.word for w in seg_words).strip()
            name = _extract_vocative_name(text)
            if not name:
                continue

            # Следующий сегмент — кандидат на голос "name"
            next_seg = segments[i + 1]

            # Пропускаем если это снова пользователь
            if next_seg.speaker == self.user_speaker:
                continue

            # Пропускаем если слишком большой зазор (другой разговор)
            gap = next_seg.start - seg.end
            if gap > _MAX_GAP_SEC:
                continue

            # Пропускаем слишком короткие сегменты (< 1.5 сек — шум)
            if next_seg.duration < 1.5:
                continue

            anchor = NameAnchor(
                name=name,
                speaker_label=next_seg.speaker,
                segment=next_seg,
                confidence=0.6,
                ingest_id=ingest_id,
            )
            anchors.append(anchor)

            logger.info(
                "name_anchor_found",
                name=name,
                speaker=next_seg.speaker,
                gap_sec=round(gap, 2),
                ingest_id=ingest_id,
            )

        return anchors
