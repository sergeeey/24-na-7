"""Async enrichment queue — fire-and-forget enrichment via asyncio workers.

ПОЧЕМУ: asyncio.to_thread(_run_enrichment_sync) блокирует thread pool worker
на 2-10 сек (LLM API call). При 5+ concurrent WebSocket streams thread pool
(default 40 workers) быстро исчерпается. Queue с 2 workers ограничивает
concurrent LLM calls и освобождает caller для следующего аудио-сегмента.

Архитектура:
  submit(task) → asyncio.Queue → 2 worker coroutines → _run_enrichment_sync()
  Fallback: если queue не запущена (тесты) — inline execution через to_thread.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from src.utils.logging import get_logger

logger = get_logger("enrichment.worker")

_NUM_WORKERS = 2
_QUEUE_MAXSIZE = 100
_MAX_ENRICHMENT_RETRIES = 2
_RETRY_DELAY_SECONDS = 5


@dataclass
class EnrichmentTask:
    """Один enrichment job для очереди."""
    db_path: Path
    transcription_id: str
    result: dict[str, Any]
    enrichment_text: str
    acoustic_metadata: dict[str, Any] | None = None
    attempt: int = 0


class EnrichmentWorker:
    """Manages async enrichment queue and worker coroutines."""

    def __init__(self, num_workers: int = _NUM_WORKERS, maxsize: int = _QUEUE_MAXSIZE) -> None:
        self._num_workers = num_workers
        self._queue: asyncio.Queue[EnrichmentTask | None] = asyncio.Queue(maxsize=maxsize)
        self._workers: list[asyncio.Task] = []
        self._running = False

    @property
    def running(self) -> bool:
        return self._running

    async def start(self) -> None:
        """Start worker coroutines. Call from lifespan startup."""
        if self._running:
            return
        self._running = True
        for i in range(self._num_workers):
            task = asyncio.create_task(self._worker_loop(i))
            self._workers.append(task)
        logger.info("enrichment_workers_started", count=self._num_workers)

    async def stop(self) -> None:
        """Drain queue and stop workers. Call from lifespan shutdown."""
        if not self._running:
            return
        self._running = False
        # Посылаем sentinel (None) каждому worker для graceful shutdown
        for _ in self._workers:
            await self._queue.put(None)
        # Ждём завершения всех workers (с timeout)
        await asyncio.gather(*self._workers, return_exceptions=True)
        self._workers.clear()
        logger.info("enrichment_workers_stopped", pending=self._queue.qsize())

    async def submit(self, task: EnrichmentTask) -> None:
        """Submit enrichment task. Falls back to inline if queue not running."""
        if self._running:
            try:
                self._queue.put_nowait(task)
                return
            except asyncio.QueueFull:
                logger.warning("enrichment_queue_full", dropping=task.transcription_id)
                return

        # Fallback: inline execution (для тестов или если worker не запущен)
        await asyncio.to_thread(self._execute, task)

    def _schedule_retry(self, task: EnrichmentTask, ingest_id: str, error: Exception) -> bool:
        """Requeue failed enrichment task with bounded retry counter."""
        from src.storage.db import get_reflexio_db

        next_attempt = task.attempt + 1
        if next_attempt > _MAX_ENRICHMENT_RETRIES:
            return False

        db = get_reflexio_db(task.db_path)
        retry_at = datetime.now() + timedelta(seconds=_RETRY_DELAY_SECONDS)
        with db.transaction():
            db.execute(
                """
                UPDATE ingest_queue
                SET status='event_pending',
                    processing_status='event_pending',
                    attempt_count=?,
                    next_attempt_at=?,
                    error_code='enrichment_retry_pending',
                    error_message=?
                WHERE id=?
                """,
                (next_attempt, retry_at.isoformat(), str(error), ingest_id),
            )

        if not self._running or not self._workers:
            return False

        asyncio.run_coroutine_threadsafe(
            self._requeue_after_delay(
                EnrichmentTask(
                    db_path=task.db_path,
                    transcription_id=task.transcription_id,
                    result=task.result,
                    enrichment_text=task.enrichment_text,
                    acoustic_metadata=task.acoustic_metadata,
                    attempt=next_attempt,
                ),
                delay_seconds=_RETRY_DELAY_SECONDS,
            ),
            self._workers[0].get_loop(),
        )
        logger.warning(
            "enrichment_task_retry_scheduled",
            transcription_id=task.transcription_id,
            ingest_id=ingest_id,
            attempt=next_attempt,
            max_attempts=_MAX_ENRICHMENT_RETRIES,
            retry_delay_seconds=_RETRY_DELAY_SECONDS,
            error=str(error),
        )
        return True

    async def _requeue_after_delay(self, task: EnrichmentTask, *, delay_seconds: int) -> None:
        await asyncio.sleep(delay_seconds)
        try:
            await self.submit(task)
        except Exception as e:
            logger.warning(
                "enrichment_retry_enqueue_failed",
                transcription_id=task.transcription_id,
                attempt=task.attempt,
                error=str(e),
            )

    def _execute(self, task: EnrichmentTask) -> None:
        """Run enrichment synchronously (called from worker or to_thread)."""
        from src.core.audio_processing import _mark_ingest_status, _run_enrichment_sync
        from src.storage.db import get_reflexio_db
        try:
            _run_enrichment_sync(
                db_path=task.db_path,
                transcription_id=task.transcription_id,
                result=task.result,
                enrichment_text=task.enrichment_text,
                acoustic_metadata=task.acoustic_metadata,
            )
            ingest_id = task.result.get("ingest_id")
            if ingest_id:
                db = get_reflexio_db(task.db_path)
                with db.transaction():
                    db.execute(
                        """
                        UPDATE ingest_queue
                        SET error_code=NULL,
                            error_message=NULL,
                            next_attempt_at=NULL
                        WHERE id=?
                        """,
                        (ingest_id,),
                    )
                _mark_ingest_status(
                    task.db_path,
                    ingest_id,
                    "event_ready",
                    transport_status="server_acked",
                    processing_status="event_ready",
                    error_code=None,
                    quality_score=task.result.get("quality_score"),
                    needs_recheck=task.result.get("needs_recheck"),
                )
        except Exception as e:
            ingest_id = task.result.get("ingest_id")
            if ingest_id and self._schedule_retry(task, ingest_id, e):
                return
            if ingest_id:
                db = get_reflexio_db(task.db_path)
                with db.transaction():
                    db.execute(
                        """
                        UPDATE ingest_queue
                        SET next_attempt_at=NULL
                        WHERE id=?
                        """,
                        (ingest_id,),
                    )
                _mark_ingest_status(
                    task.db_path,
                    ingest_id,
                    "transcribed",
                    str(e),
                    transport_status="server_acked",
                    processing_status="transcribed",
                    error_code="enrichment_failed",
                    review_required=True,
                    quality_score=task.result.get("quality_score"),
                    needs_recheck=task.result.get("needs_recheck"),
                )
            logger.warning(
                "enrichment_task_failed",
                transcription_id=task.transcription_id,
                attempt=task.attempt,
                error=str(e),
            )

    async def _worker_loop(self, worker_id: int) -> None:
        """One worker coroutine — pulls tasks from queue and processes them."""
        logger.debug("enrichment_worker_started", worker_id=worker_id)
        while True:
            task = await self._queue.get()
            if task is None:
                # Sentinel — shutdown signal
                self._queue.task_done()
                break
            try:
                await asyncio.to_thread(self._execute, task)
            finally:
                self._queue.task_done()
        logger.debug("enrichment_worker_stopped", worker_id=worker_id)


# Module-level singleton — создаётся при импорте, запускается в lifespan
_worker: EnrichmentWorker | None = None


def get_enrichment_worker() -> EnrichmentWorker:
    """Return or create the module-level EnrichmentWorker singleton."""
    global _worker
    if _worker is None:
        _worker = EnrichmentWorker()
    return _worker
