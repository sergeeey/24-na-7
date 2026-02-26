"""Circuit Breaker для защиты от каскадных отказов внешних зависимостей."""
import time
from typing import Callable, Optional, TypeVar, Any
from enum import Enum
from functools import wraps

from src.utils.logging import get_logger

logger = get_logger("utils.circuit_breaker")

T = TypeVar("T")


class CircuitState(Enum):
    """Состояния circuit breaker."""
    CLOSED = "closed"  # Нормальная работа
    OPEN = "open"  # Открыт, запросы блокируются
    HALF_OPEN = "half_open"  # Тестовый режим


class CircuitBreakerError(Exception):
    """Исключение при открытом circuit breaker."""
    pass


class CircuitBreaker:
    """
    Circuit Breaker для защиты от каскадных отказов.
    
    Принцип работы:
    - CLOSED: запросы проходят нормально
    - При failure_threshold ошибок подряд → OPEN
    - После timeout секунд → HALF_OPEN (тестовый режим)
    - В HALF_OPEN: если успех → CLOSED, если ошибка → OPEN
    
    Args:
        failure_threshold: Количество ошибок для открытия (default: 5)
        timeout: Время в секундах до перехода в HALF_OPEN (default: 60)
        expected_exception: Тип исключения для отслеживания (default: Exception)
        name: Имя circuit breaker для логирования
    """
    
    def __init__(
        self,
        failure_threshold: int = 5,
        timeout: int = 60,
        expected_exception: type[Exception] = Exception,
        name: str = "circuit_breaker",
    ):
        self.failure_threshold = failure_threshold
        self.timeout = timeout
        self.expected_exception = expected_exception
        self.name = name
        
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.last_failure_time: Optional[float] = None
        self.success_count = 0  # Для HALF_OPEN режима
        
    def call(self, func: Callable[..., T], *args: Any, **kwargs: Any) -> T:
        """
        Выполняет функцию через circuit breaker.
        
        Args:
            func: Функция для выполнения
            *args: Аргументы функции
            **kwargs: Ключевые аргументы функции
            
        Returns:
            Результат выполнения функции
            
        Raises:
            CircuitBreakerError: Если circuit breaker открыт
            Exception: Исходное исключение от функции
        """
        # Проверяем состояние
        if self.state == CircuitState.OPEN:
            # Проверяем можно ли перейти в HALF_OPEN
            if self.last_failure_time and (time.time() - self.last_failure_time) >= self.timeout:
                logger.info(
                    "circuit_breaker_half_open",
                    name=self.name,
                    timeout=self.timeout,
                )
                self.state = CircuitState.HALF_OPEN
                self.success_count = 0
            else:
                raise CircuitBreakerError(
                    f"Circuit breaker '{self.name}' is OPEN. "
                    f"Last failure: {self.last_failure_time}. "
                    f"Retry after {self.timeout} seconds."
                )
        
        # Выполняем функцию
        try:
            result = func(*args, **kwargs)
            
            # Успешное выполнение
            self._on_success()
            return result
            
        except self.expected_exception:
            # Ошибка отслеживаемого типа
            self._on_failure()
            raise
        
        except Exception as e:
            # Другие ошибки не отслеживаем
            logger.warning(
                "circuit_breaker_unexpected_error",
                name=self.name,
                error_type=type(e).__name__,
                error=str(e),
            )
            raise
    
    def _on_success(self) -> None:
        """Обработка успешного выполнения."""
        if self.state == CircuitState.HALF_OPEN:
            # В HALF_OPEN режиме нужен один успех для закрытия
            self.success_count += 1
            if self.success_count >= 1:
                logger.info(
                    "circuit_breaker_closed",
                    name=self.name,
                    success_count=self.success_count,
                )
                self.state = CircuitState.CLOSED
                self.failure_count = 0
                self.success_count = 0
        else:
            # В CLOSED режиме сбрасываем счётчик ошибок
            self.failure_count = 0
    
    def _on_failure(self) -> None:
        """Обработка ошибки."""
        self.failure_count += 1
        self.last_failure_time = time.time()
        
        logger.warning(
            "circuit_breaker_failure",
            name=self.name,
            failure_count=self.failure_count,
            threshold=self.failure_threshold,
            state=self.state.value,
        )
        
        if self.state == CircuitState.HALF_OPEN:
            # В HALF_OPEN режиме любая ошибка открывает circuit breaker
            logger.error(
                "circuit_breaker_opened_from_half_open",
                name=self.name,
            )
            self.state = CircuitState.OPEN
            self.success_count = 0
        elif self.failure_count >= self.failure_threshold:
            # Достигли порога ошибок
            logger.error(
                "circuit_breaker_opened",
                name=self.name,
                failure_count=self.failure_count,
                threshold=self.failure_threshold,
            )
            self.state = CircuitState.OPEN
    
    def reset(self) -> None:
        """Сброс circuit breaker в начальное состояние."""
        logger.info("circuit_breaker_reset", name=self.name)
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.last_failure_time = None
        self.success_count = 0
    
    def get_state(self) -> CircuitState:
        """Возвращает текущее состояние."""
        return self.state
    
    def get_stats(self) -> dict[str, Any]:
        """Возвращает статистику circuit breaker."""
        return {
            "name": self.name,
            "state": self.state.value,
            "failure_count": self.failure_count,
            "failure_threshold": self.failure_threshold,
            "last_failure_time": self.last_failure_time,
            "timeout": self.timeout,
        }


def circuit_breaker_decorator(
    failure_threshold: int = 5,
    timeout: int = 60,
    expected_exception: type[Exception] = Exception,
    name: Optional[str] = None,
):
    """
    Декоратор для применения circuit breaker к функции.
    
    Args:
        failure_threshold: Количество ошибок для открытия
        timeout: Время до перехода в HALF_OPEN
        expected_exception: Тип исключения для отслеживания
        name: Имя circuit breaker (по умолчанию имя функции)
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        breaker_name = name or f"{func.__module__}.{func.__name__}"
        breaker = CircuitBreaker(
            failure_threshold=failure_threshold,
            timeout=timeout,
            expected_exception=expected_exception,
            name=breaker_name,
        )
        
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            return breaker.call(func, *args, **kwargs)
        
        # Добавляем методы для управления
        wrapper.circuit_breaker = breaker  # type: ignore
        wrapper.reset_circuit_breaker = breaker.reset  # type: ignore
        wrapper.get_circuit_breaker_state = breaker.get_state  # type: ignore
        wrapper.get_circuit_breaker_stats = breaker.get_stats  # type: ignore
        
        return wrapper
    
    return decorator
