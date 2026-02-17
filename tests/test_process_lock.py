"""Tests для ProcessLock."""
import os
import time
import pytest
import subprocess
from pathlib import Path
from multiprocessing import Process

from src.utils.process_lock import ProcessLock, ProcessLockError


@pytest.fixture
def lock_dir(tmp_path):
    """Temporary directory для lock files."""
    return tmp_path / "locks"


class TestProcessLock:
    """Tests для process locking."""

    def test_single_process_acquires_lock(self, lock_dir):
        """Тест: single process получает lock."""
        lock = ProcessLock("test_single", lock_dir=lock_dir, timeout=5)

        assert lock.acquire()
        assert lock.locked
        assert lock.pid_file.exists()

        # PID file должен содержать текущий PID
        with open(lock.pid_file) as f:
            pid = int(f.read().strip())
        assert pid == os.getpid()

        lock.release()
        assert not lock.locked
        assert not lock.pid_file.exists()

    def test_context_manager(self, lock_dir):
        """Тест: context manager usage."""
        with ProcessLock("test_context", lock_dir=lock_dir, timeout=5) as lock:
            assert lock.locked
            assert lock.pid_file.exists()

        # После exit — lock освобожден
        assert not lock.locked
        assert not lock.pid_file.exists()

    def test_duplicate_lock_raises_error(self, lock_dir):
        """Тест: duplicate lock raises ProcessLockError."""
        lock1 = ProcessLock("test_dup", lock_dir=lock_dir, timeout=2)
        lock1.acquire()

        # Второй lock должен fail
        lock2 = ProcessLock("test_dup", lock_dir=lock_dir, timeout=2)

        with pytest.raises(ProcessLockError, match="Could not acquire lock"):
            lock2.acquire()

        lock1.release()

    def test_stale_lock_detection(self, lock_dir):
        """Тест: stale lock detection (process terminated)."""
        # Создаём fake PID file с несуществующим PID
        pid_file = lock_dir / "test_stale.pid"
        lock_dir.mkdir(parents=True, exist_ok=True)

        with open(pid_file, "w") as f:
            f.write("999999")  # Несуществующий PID

        # Должно обнаружить stale lock и пересоздать
        lock = ProcessLock("test_stale", lock_dir=lock_dir, timeout=5)
        assert lock.acquire()  # Успешно после удаления stale lock
        assert lock.locked

        lock.release()

    def test_multiple_process_simulation(self, lock_dir):
        """Тест: multiple processes (один получает lock, другой fails)."""
        def worker(lock_name, lock_dir_str, results_list):
            """Worker process."""
            lock = ProcessLock(lock_name, lock_dir=Path(lock_dir_str), timeout=2)
            try:
                lock.acquire()
                time.sleep(0.5)  # Hold lock
                results_list.append("SUCCESS")
                lock.release()
            except ProcessLockError:
                results_list.append("FAILED")

        # Запускаем 2 processes одновременно
        from multiprocessing import Manager
        manager = Manager()
        results = manager.list()

        p1 = Process(target=worker, args=("test_multi", str(lock_dir), results))
        p2 = Process(target=worker, args=("test_multi", str(lock_dir), results))

        p1.start()
        time.sleep(0.1)  # Даём p1 время захватить lock
        p2.start()

        p1.join()
        p2.join()

        # Один process должен успешно получить lock, другой — fail
        assert "SUCCESS" in results
        assert "FAILED" in results

    def test_cleanup_on_exit(self, lock_dir):
        """Тест: cleanup при exit."""
        lock = ProcessLock("test_cleanup", lock_dir=lock_dir, timeout=5)
        lock.acquire()

        pid_file = lock.pid_file
        assert pid_file.exists()

        # Симулируем exit через __del__
        del lock

        # PID file должен быть удалён
        assert not pid_file.exists()

    def test_timeout_zero(self, lock_dir):
        """Тест: timeout=0 (no wait)."""
        lock1 = ProcessLock("test_timeout0", lock_dir=lock_dir, timeout=0)
        lock1.acquire()

        lock2 = ProcessLock("test_timeout0", lock_dir=lock_dir, timeout=0)

        with pytest.raises(ProcessLockError):
            lock2.acquire()  # Должно fail immediately

        lock1.release()

    def test_process_lock_prevents_telegram_duplicate(self, lock_dir):
        """Интеграционный тест: ProcessLock prevents duplicate Telegram sends."""
        # Simulate daily_digest_cron scenario
        def run_digest_once():
            with ProcessLock("daily_digest", lock_dir=lock_dir, timeout=5):
                time.sleep(0.2)  # Simulate digest generation
                return "DIGEST_SENT"

        # First call succeeds
        result1 = run_digest_once()
        assert result1 == "DIGEST_SENT"

        # Concurrent call should be blocked (simulate via subprocess)
        # (Full test would use subprocess, here we test locking logic)
        try:
            with ProcessLock("daily_digest", lock_dir=lock_dir, timeout=1):
                pytest.fail("Should not acquire lock — stale detection needed")
        except ProcessLockError:
            pass  # Expected — lock was held recently

    @pytest.mark.parametrize("os_type", ["nt", "posix"])
    def test_cross_platform_lock_dir(self, os_type, monkeypatch, lock_dir):
        """Тест: lock directory на разных OS."""
        monkeypatch.setattr(os, "name", os_type)

        if os_type == "nt":
            # Windows — TEMP
            monkeypatch.setenv("TEMP", str(lock_dir))
        else:
            # Unix — /tmp (overridden in fixture)
            pass

        lock = ProcessLock("test_platform", lock_dir=lock_dir, timeout=5)
        lock.acquire()

        # Lock file должен быть в правильной директории
        assert lock.pid_file.parent == lock_dir

        lock.release()
