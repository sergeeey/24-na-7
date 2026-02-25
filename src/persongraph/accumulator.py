"""
VoiceProfileAccumulator — накопление голосовых профилей окружения.

Жизненный цикл сэмпла:
  NameAnchor найден → embed_audio() → save_sample() → accumulating
    → count >= MIN_SAMPLES AND avg_conf >= MIN_CONFIDENCE
    → status = pending_approval → уведомление пользователю
    → пользователь нажал "Да" → approve_profile()
    → person_voice_profiles: усреднённый d-vector создан

Compliance:
  - Профиль создаётся ТОЛЬКО после явного подтверждения пользователем
  - TTL реализован в compliance.py (запускается ежедневно)
  - Право на удаление: delete_person_data()

ПОЧЕМУ 10 сэмплов:
  GE2E paper (Wan et al., 2018): d-vector стабилизируется после 10+
  utterances. С меньшим числом cosine similarity нестабильна.
"""
from __future__ import annotations

import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from enum import Enum
from pathlib import Path
from typing import Optional

import numpy as np

from src.speaker.embedder import embed_audio
from src.utils.logging import get_logger

logger = get_logger("persongraph.accumulator")

# ──────────────────────────────────────────────
# Константы
# ──────────────────────────────────────────────

MIN_SAMPLES: int = 10          # минимум сэмплов для формирования профиля
MIN_CONFIDENCE: float = 0.85   # минимум средней уверенности якорей
PROFILE_TTL_DAYS: int = 365    # ежегодное переподтверждение


# ──────────────────────────────────────────────
# Типы данных
# ──────────────────────────────────────────────

class ProfileStatus(Enum):
    ACCUMULATING      = "accumulating"        # мало сэмплов
    PENDING_APPROVAL  = "pending_approval"    # достаточно, ждём пользователя
    APPROVED          = "approved"            # профиль подтверждён
    REJECTED          = "rejected"            # пользователь отклонил


@dataclass
class AccumulationResult:
    person_name: str
    status: ProfileStatus
    sample_count: int
    avg_confidence: float
    ready_for_approval: bool = False    # True = нужно уведомить пользователя


# ──────────────────────────────────────────────
# Основной класс
# ──────────────────────────────────────────────

class VoiceProfileAccumulator:
    """
    Накапливает GE2E-сэмплы голосов окружения и строит усреднённые профили.

    Использование:
        acc = VoiceProfileAccumulator(db_path)
        result = acc.add_sample(
            name="Максим",
            audio=audio_float32,
            anchor_confidence=0.65,
            ingest_id="abc-123"
        )
        if result.ready_for_approval:
            # Отправить push-уведомление пользователю
            notify_user(result.person_name)
    """

    def __init__(self, db_path: Path):
        self.db_path = db_path

    # ── Публичный API ──────────────────────────

    def add_sample(
        self,
        name: str,
        audio: np.ndarray,
        anchor_confidence: float,
        ingest_id: str = "",
        sample_rate: int = 16000,
    ) -> AccumulationResult:
        """
        Добавляет голосовой сэмпл для персоны.

        Args:
            name:             Имя персоны ("Максим")
            audio:            float32 аудио-сегмент [-1, 1]
            anchor_confidence: Уверенность якоря (0.0–1.0)
            ingest_id:        ID источника записи
            sample_rate:      Частота дискретизации

        Returns:
            AccumulationResult со статусом и флагом ready_for_approval
        """
        # Вычисляем embedding
        try:
            embedding: np.ndarray = embed_audio(audio, sample_rate)
        except Exception as e:
            logger.warning("embed_failed", name=name, error=str(e))
            raise

        # Убеждаемся что персона существует
        self._ensure_person(name)

        # Сохраняем сэмпл
        sample_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()

        conn = self._connect()
        try:
            conn.execute(
                """
                INSERT INTO person_voice_samples
                    (id, person_name, embedding, anchor_conf, status, source_ingest, created_at)
                VALUES (?, ?, ?, ?, 'accumulating', ?, ?)
                """,
                (sample_id, name, embedding.tobytes(), anchor_confidence, ingest_id, now),
            )

            # Обновляем счётчик сэмплов у персоны
            conn.execute(
                """
                UPDATE persons
                SET sample_count = sample_count + 1,
                    last_seen = ?
                WHERE name = ?
                """,
                (now[:10], name),  # только дата
            )
            conn.commit()
        finally:
            conn.close()

        logger.info(
            "voice_sample_saved",
            name=name,
            sample_id=sample_id[:8],
            anchor_conf=round(anchor_confidence, 3),
        )

        # Проверяем готовность к подтверждению
        return self._check_threshold(name)

    def approve_profile(self, person_name: str) -> bool:
        """
        Пользователь подтвердил профиль — создаём усреднённый d-vector.

        Args:
            person_name: Имя персоны

        Returns:
            True если профиль успешно создан
        """
        conn = self._connect()
        try:
            rows = conn.execute(
                """
                SELECT embedding, anchor_conf FROM person_voice_samples
                WHERE person_name = ? AND status IN ('accumulating', 'pending_approval')
                """,
                (person_name,),
            ).fetchall()

            if not rows:
                logger.warning("approve_no_samples", name=person_name)
                return False

            # Взвешенное среднее: вес = anchor_confidence
            embeddings = []
            weights = []
            for row in rows:
                emb = np.frombuffer(row[0], dtype=np.float32)
                embeddings.append(emb)
                weights.append(float(row[1]) if row[1] else 0.5)

            # Нормализованное взвешенное среднее → на единичную сферу
            weights_arr = np.array(weights, dtype=np.float32)
            weights_arr /= weights_arr.sum()
            avg_emb = np.average(embeddings, axis=0, weights=weights_arr)
            avg_emb /= np.linalg.norm(avg_emb)  # нормализация на единичную сферу

            now = datetime.now(timezone.utc)
            expires = now + timedelta(days=PROFILE_TTL_DAYS)

            # Сохраняем финальный профиль
            conn.execute(
                """
                INSERT OR REPLACE INTO person_voice_profiles
                    (person_name, avg_embedding, sample_count, avg_confidence,
                     approved_at, expires_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    person_name,
                    avg_emb.tobytes(),
                    len(rows),
                    float(np.mean(weights)),
                    now.isoformat(),
                    expires.isoformat(),
                ),
            )

            # Помечаем все сэмплы как approved
            conn.execute(
                "UPDATE person_voice_samples SET status = 'approved' WHERE person_name = ?",
                (person_name,),
            )

            # Обновляем флаг voice_ready у персоны
            conn.execute(
                "UPDATE persons SET voice_ready = 1, approved_at = ? WHERE name = ?",
                (now.isoformat(), person_name),
            )
            conn.commit()

            logger.info(
                "voice_profile_approved",
                name=person_name,
                samples=len(rows),
                expires=expires.date().isoformat(),
            )
            return True

        except Exception as e:
            conn.rollback()
            logger.error("approve_profile_failed", name=person_name, error=str(e))
            return False
        finally:
            conn.close()

    def reject_profile(self, person_name: str) -> None:
        """Пользователь отклонил профиль — удаляем все сэмплы немедленно."""
        conn = self._connect()
        try:
            conn.execute(
                "UPDATE person_voice_samples SET status = 'rejected' WHERE person_name = ?",
                (person_name,),
            )
            conn.execute(
                "DELETE FROM person_voice_samples WHERE person_name = ? AND status = 'rejected'",
                (person_name,),
            )
            conn.commit()
            logger.info("voice_profile_rejected_cleaned", name=person_name)
        finally:
            conn.close()

    def load_profile(self, person_name: str) -> Optional[np.ndarray]:
        """
        Загружает усреднённый d-vector для идентификации голоса.

        Returns:
            np.ndarray(256,) float32 или None если профиля нет
        """
        conn = self._connect()
        try:
            row = conn.execute(
                """
                SELECT avg_embedding FROM person_voice_profiles
                WHERE person_name = ?
                AND expires_at > ?
                """,
                (person_name, datetime.now(timezone.utc).isoformat()),
            ).fetchone()

            if not row:
                return None
            return np.frombuffer(row[0], dtype=np.float32).copy()
        finally:
            conn.close()

    def get_pending_approvals(self) -> list[dict]:
        """Возвращает список персон, ожидающих подтверждения пользователем."""
        conn = self._connect()
        try:
            rows = conn.execute(
                """
                SELECT p.name, p.sample_count,
                       AVG(pvs.anchor_conf) as avg_conf,
                       MIN(pvs.created_at) as first_sample
                FROM persons p
                JOIN person_voice_samples pvs ON pvs.person_name = p.name
                WHERE pvs.status = 'pending_approval'
                GROUP BY p.name
                """,
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    # ── Приватные методы ───────────────────────

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_person(self, name: str) -> None:
        """Создаёт запись персоны если её ещё нет."""
        conn = self._connect()
        try:
            today = datetime.now(timezone.utc).date().isoformat()
            conn.execute(
                """
                INSERT OR IGNORE INTO persons (id, name, first_seen, last_seen)
                VALUES (?, ?, ?, ?)
                """,
                (str(uuid.uuid4()), name, today, today),
            )
            conn.commit()
        finally:
            conn.close()

    def _check_threshold(self, name: str) -> AccumulationResult:
        """Проверяет достигнут ли порог и обновляет статус сэмплов."""
        conn = self._connect()
        try:
            row = conn.execute(
                """
                SELECT COUNT(*) as cnt, AVG(anchor_conf) as avg_conf
                FROM person_voice_samples
                WHERE person_name = ?
                AND status IN ('accumulating', 'pending_approval')
                """,
                (name,),
            ).fetchone()

            count = row["cnt"] or 0
            avg_conf = float(row["avg_conf"] or 0.0)
            ready = count >= MIN_SAMPLES and avg_conf >= MIN_CONFIDENCE

            if ready:
                # Переводим все accumulating → pending_approval
                conn.execute(
                    """
                    UPDATE person_voice_samples
                    SET status = 'pending_approval'
                    WHERE person_name = ? AND status = 'accumulating'
                    """,
                    (name,),
                )
                conn.commit()
                logger.info(
                    "voice_profile_ready_for_approval",
                    name=name,
                    samples=count,
                    avg_conf=round(avg_conf, 3),
                )

            return AccumulationResult(
                person_name=name,
                status=ProfileStatus.PENDING_APPROVAL if ready else ProfileStatus.ACCUMULATING,
                sample_count=count,
                avg_confidence=round(avg_conf, 3),
                ready_for_approval=ready,
            )
        finally:
            conn.close()
