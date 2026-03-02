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
from pathlib import Path
from typing import Any

from src.utils.logging import get_logger

logger = get_logger("enrichment.worker")

_NUM_WORKERS = 2
_QUEUE_MAXSIZE = 100


@dataclass
class EnrichmentTask:
    """Один enrichment job для очереди."""
    db_path: Path
    transcription_id: str
    result: dict[str, Any]
    enrichment_text: str


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

    def _execute(self, task: EnrichmentTask) -> None:
        """Run enrichment synchronously (called from worker or to_thread)."""
        from src.core.audio_processing import _run_enrichment_sync
        try:
            _run_enrichment_sync(
                db_path=task.db_path,
                transcription_id=task.transcription_id,
                result=task.result,
                enrichment_text=task.enrichment_text,
            )
        except Exception as e:
            logger.warning(
                "enrichment_task_failed",
                transcription_id=task.transcription_id,
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
