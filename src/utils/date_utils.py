"""
resolve_date_range() — единая timezone-safe функция интерпретации периода.

ПОЧЕМУ единая функция:
  В проекте 15+ мест где парсятся даты по-разному — часть в UTC, часть без.
  DST и граничные случаи (00:00/23:59) несовместимы между роутерами.
  Централизация: один раз правильно, везде одинаково.

Использование:
  from src.utils.date_utils import resolve_date_range, DateRange

  dr = resolve_date_range("2026-03-03")
  # dr.start = datetime(2026, 3, 3, 0, 0, 0, tzinfo=UTC+6)
  # dr.end   = datetime(2026, 3, 3, 23, 59, 59, tzinfo=UTC+6)
  # dr.start_utc = datetime(2026, 3, 2, 18, 0, 0, tzinfo=UTC)
  # dr.end_utc   = datetime(2026, 3, 3, 17, 59, 59, tzinfo=UTC)
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone, date as date_type
from typing import Optional


# ПОЧЕМУ UTC+6: пользователь в Алматы. При добавлении DST — вынести в Settings.
_USER_UTC_OFFSET = 6
_USER_TZ = timezone(timedelta(hours=_USER_UTC_OFFSET))
_UTC = timezone.utc


@dataclass(frozen=True)
class DateRange:
    """Период с обеими временными зонами (локальной и UTC)."""

    start: datetime       # начало в USER_TZ (00:00:00)
    end: datetime         # конец в USER_TZ (23:59:59)
    start_utc: datetime   # начало в UTC
    end_utc: datetime     # конец в UTC
    label: str            # human-readable описание периода

    def sql_range(self) -> tuple[str, str]:
        """ISO strings для SQL WHERE created_at BETWEEN ? AND ?"""
        return (
            self.start_utc.isoformat(),
            self.end_utc.isoformat(),
        )

    def contains_now(self) -> bool:
        now_utc = datetime.now(_UTC)
        return self.start_utc <= now_utc <= self.end_utc


def resolve_date_range(
    date_str: Optional[str] = None,
    *,
    days_back: Optional[int] = None,
    start_str: Optional[str] = None,
    end_str: Optional[str] = None,
    max_days: int = 31,
) -> DateRange:
    """
    Универсальный парсер периода. Все варианты вызова:

      resolve_date_range("2026-03-03")         → один день
      resolve_date_range(days_back=7)           → последние 7 дней
      resolve_date_range(start_str=..., end_str=...) → произвольный диапазон
      resolve_date_range()                      → сегодня

    Args:
      date_str:   YYYY-MM-DD — один конкретный день
      days_back:  N — последние N дней (включая сегодня)
      start_str:  YYYY-MM-DD — начало диапазона
      end_str:    YYYY-MM-DD — конец диапазона (включительно)
      max_days:   максимальная длина диапазона (защита от data dump)

    Raises:
      ValueError: неверный формат даты или диапазон > max_days
    """
    now_user = datetime.now(_USER_TZ)
    today = now_user.date()

    # --- Выбираем режим ---
    if date_str is not None:
        target = _parse_date(date_str)
        start_local = _day_start(target)
        end_local = _day_end(target)
        label = f"{target.isoformat()}"

    elif days_back is not None:
        if days_back < 1:
            raise ValueError("days_back must be ≥ 1")
        if days_back > max_days:
            raise ValueError(f"days_back {days_back} exceeds max_days {max_days}")
        start_d = today - timedelta(days=days_back - 1)
        start_local = _day_start(start_d)
        end_local = _day_end(today)
        label = f"last_{days_back}_days"

    elif start_str is not None or end_str is not None:
        if start_str is None or end_str is None:
            raise ValueError("Both start_str and end_str are required")
        s = _parse_date(start_str)
        e = _parse_date(end_str)
        if e < s:
            raise ValueError("end_str must be >= start_str")
        delta = (e - s).days + 1
        if delta > max_days:
            raise ValueError(
                f"Date range {delta} days exceeds limit {max_days}. Use narrower range."
            )
        start_local = _day_start(s)
        end_local = _day_end(e)
        label = f"{s.isoformat()}_{e.isoformat()}"

    else:
        # Сегодня по умолчанию
        start_local = _day_start(today)
        end_local = _day_end(today)
        label = "today"

    start_utc = start_local.astimezone(_UTC)
    end_utc = end_local.astimezone(_UTC)

    return DateRange(
        start=start_local,
        end=end_local,
        start_utc=start_utc,
        end_utc=end_utc,
        label=label,
    )


# --- helpers ---

def _parse_date(s: str) -> date_type:
    try:
        return datetime.strptime(s.strip(), "%Y-%m-%d").date()
    except ValueError:
        raise ValueError(f"Invalid date format '{s}'. Use YYYY-MM-DD.")


def _day_start(d: date_type) -> datetime:
    return datetime(d.year, d.month, d.day, 0, 0, 0, tzinfo=_USER_TZ)


def _day_end(d: date_type) -> datetime:
    return datetime(d.year, d.month, d.day, 23, 59, 59, tzinfo=_USER_TZ)
