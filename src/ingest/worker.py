"""Очередь обработки ingest: принятый WAV обрабатывается в фоне (ASR + enrichment).

ПОЧЕМУ: WebSocket сразу отвечает «received», тяжёлую работу выполняет IngestWorker.
Прокси не держит соединение 30–120 сек → нет 502. Результат доставляется в то же
соединение через реестр (connection_id -> Queue).
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.core.audio_processing import process_audio_from_artifact_sync
from src.storage.db import get_reflexio_db
from src.utils.logging import get_logger

logger = get_logger("ingest.worker")

_NUM_WORKERS = 2
_QUEUE_MAXSIZE = 200
_RECOVERABLE_ERROR_CODES = {
    "asr_runtime_error",
    "watchdog_stuck_pending",
    "watchdog_stuck_received",
    "watchdog_stuck_asr_pending",
}


@dataclass
class IngestTask:
    """Одна задача обработки уже сохранённого артефакта."""
    ingest_id: str
    file_path: Path
    connection_id: str
    enrichment_prefix: str | None = None


class IngestWorker:
    """Очередь задач ingest: воркеры вызывают process_audio_from_artifact_sync и доставляют результат в реестр."""

    def __init__(
        self,
        registry: dict[str, asyncio.Queue[dict[str, Any] | None]],
        num_workers: int = _NUM_WORKERS,
        maxsize: int = _QUEUE_MAXSIZE,
    ) -> None:
        self._registry = registry
        self._num_workers = num_workers
        self._queue: asyncio.Queue[IngestTask | None] = asyncio.Queue(maxsize=maxsize)
        self._workers: list[asyncio.Task] = []
        self._running = False

    @property
    def running(self) -> bool:
        return self._running

    async def start(self) -> None:
        """Запуск воркеров. Вызывать из lifespan startup."""
        if self._running:
            return
        self._running = True
        for i in range(self._num_workers):
            task = asyncio.create_task(self._worker_loop(i))
            self._workers.append(task)
        logger.info("ingest_workers_started", count=self._num_workers)

    async def stop(self) -> None:
        """Остановка воркеров. Вызывать из lifespan shutdown."""
        if not self._running:
            return
        self._running = False
        for _ in self._workers:
            await self._queue.put(None)
        await asyncio.gather(*self._workers, return_exceptions=True)
        self._workers.clear()
        logger.info("ingest_workers_stopped", pending=self._queue.qsize())

    def submit(self, task: IngestTask) -> bool:
        """Поставить задачу в очередь. Возвращает False при перегрузе или если worker не запущен."""
        if not self._running:
            logger.warning("ingest_worker_not_running", ingest_id=task.ingest_id)
            return False
        try:
            self._queue.put_nowait(task)
            return True
        except asyncio.QueueFull:
            logger.warning("ingest_queue_full", dropping=task.ingest_id)
            return False

    def _deliver(self, connection_id: str, msg: dict[str, Any]) -> None:
        """Положить сообщение в очередь соединения, если оно ещё в реестре."""
        q = self._registry.get(connection_id)
        if q is None:
            logger.debug("ingest_deliver_skipped_disconnected", connection_id=connection_id)
            return
        try:
            q.put_nowait(msg)
        except asyncio.QueueFull:
            logger.warning("ingest_deliver_queue_full", connection_id=connection_id)

    def _execute(self, task: IngestTask) -> None:
        """Синхронная обработка: ASR + enrichment, затем доставка результата в реестр."""
        try:
            result = process_audio_from_artifact_sync(
                ingest_id=task.ingest_id,
                file_path=task.file_path,
                enrichment_prefix=task.enrichment_prefix,
                transcription_stage="ws_transcription_saved",
                delete_audio_after=True,
                run_enrichment=True,
            )
        except Exception as e:
            logger.warning("ingest_task_failed", ingest_id=task.ingest_id, error=str(e))
            self._deliver(
                task.connection_id,
                {"type": "error", "file_id": task.ingest_id, "message": "Audio processing error"},
            )
            return

        status = result.get("status")
        if status == "filtered":
            self._deliver(
                task.connection_id,
                {
                    "type": "filtered",
                    "file_id": task.ingest_id,
                    "reason": result.get("reason", "filtered"),
                    "language": result.get("language"),
                    "delete_audio": True,
                },
            )
            return
        if status == "quarantined":
            self._deliver(
                task.connection_id,
                {
                    "type": "error",
                    "file_id": task.ingest_id,
                    "message": result.get("reason", "quarantined"),
                },
            )
            return
        if status != "transcribed":
            self._deliver(
                task.connection_id,
                {
                    "type": "error",
                    "file_id": task.ingest_id,
                    "message": result.get("reason", "processing_failed"),
                },
            )
            return

        payload = result.get("result", {})
        self._deliver(
            task.connection_id,
            {
                "type": "transcription",
                "file_id": task.ingest_id,
                "text": payload.get("text", ""),
                "language": payload.get("language", ""),
                "delete_audio": True,
                "privacy_mode": payload.get("privacy_mode", "audit"),
            },
        )

    async def _worker_loop(self, worker_id: int) -> None:
        """Один воркер: берёт задачу из очереди, выполняет в to_thread, доставляет результат."""
        logger.debug("ingest_worker_started", worker_id=worker_id)
        while True:
            task = await self._queue.get()
            if task is None:
                self._queue.task_done()
                break
            try:
                await asyncio.to_thread(self._execute, task)
            finally:
                self._queue.task_done()
        logger.debug("ingest_worker_stopped", worker_id=worker_id)


_worker: IngestWorker | None = None


def get_ingest_worker(registry: dict[str, asyncio.Queue[dict[str, Any] | None]]) -> IngestWorker:
    """Вернуть или создать singleton IngestWorker. Реестр передаётся при первом вызове (из lifespan)."""
    global _worker
    if _worker is None:
        _worker = IngestWorker(registry=registry)
    return _worker


def recover_retryable_ingest_tasks(
    worker: IngestWorker,
    *,
    db_path: Path,
    limit: int = 25,
) -> dict[str, int]:
    """Requeue bounded retryable ingest backlog from SQLite into the in-memory worker."""
    if not worker.running:
        logger.warning("ingest_recovery_skipped_worker_not_running")
        return {"requeued": 0, "missing_audio": 0}

    db = get_reflexio_db(db_path)
    rows = db.fetchall(
        """
        SELECT id, file_path, error_code
        FROM ingest_queue
        WHERE status = 'retryable_error'
          AND error_code IN (?, ?, ?, ?)
        ORDER BY created_at ASC
        LIMIT ?
        """,
        (*sorted(_RECOVERABLE_ERROR_CODES), limit),
    )

    requeued = 0
    missing_audio = 0
    for row in rows:
        file_path = Path(row["file_path"])
        if not file_path.exists():
            with db.transaction():
                db.execute(
                    """
                    UPDATE ingest_queue
                    SET status='quarantined',
                        processing_status='quarantined',
                        error_code='missing_audio',
                        quarantine_reason='missing_audio',
                        error_message='Audio artifact missing'
                    WHERE id=?
                    """,
                    (row["id"],),
                )
            missing_audio += 1
            continue

        with db.transaction():
            db.execute(
                """
                UPDATE ingest_queue
                SET status='received',
                    processing_status='received',
                    error_code=NULL,
                    error_message=NULL,
                    quarantine_reason=NULL,
                    processed_at=NULL
                WHERE id=?
                """,
                (row["id"],),
            )
        worker.submit(
            IngestTask(
                ingest_id=row["id"],
                file_path=file_path,
                connection_id="recovery",
                enrichment_prefix=None,
            )
        )
        requeued += 1

    if requeued or missing_audio:
        logger.info(
            "ingest_recovery_enqueued",
            requeued=requeued,
            missing_audio=missing_audio,
            scanned=len(rows),
        )
    return {"requeued": requeued, "missing_audio": missing_audio}
