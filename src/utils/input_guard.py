"""
Input Guard — защита от prompt injection и вредоносных входных данных.

Security Features:
- Prompt Injection Detection
- Jailbreak Prevention  
- PII Detection (basic)
- Input Sanitization
"""
import re
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

from src.utils.logging import get_logger

logger = get_logger("input_guard")


class ThreatLevel(Enum):
    """Уровень угрозы обнаруженной атаки."""
    LOW = "low"           # Подозрительно, но безопасно
    MEDIUM = "medium"     # Требует внимания
    HIGH = "high"         # Вероятная атака
    CRITICAL = "critical" # Определенная атака


@dataclass
class GuardResult:
    """Результат проверки input guard."""
    is_safe: bool
    threat_level: ThreatLevel
    threats_detected: List[str]
    sanitized_input: Optional[str]
    reason: str


class PromptInjectionDetector:
    """
    Детектор prompt injection атак.
    
    Обнаруживает:
    - Попытки изменить системные инструкции
    - Jailbreak техники
    - Кодированные атаки (base64, etc)
    - Многоязычные атаки
    """
    
    # Паттерны для обнаружения
    INJECTION_PATTERNS = {
        "system_override": [
            r"ignore\s+(?:all\s+)?(?:previous|prior)\s+(?:instructions|directives|commands)",
            r"disregard\s+(?:all\s+)?(?:previous|prior)\s+(?:instructions|directives)",
            r"system\s*:\s*",
            r"system\s+prompt",
            r"you\s+are\s+now",
            r"you\s+are\s+in\s+[^.]*mode",
            r"developer\s*:\s*",
            r"admin\s*:\s*",
        ],
        "jailbreak": [
            r"\bDAN\b",
            r"do\s+anything\s+now",
            r"jailbreak",
            r"\bSTAN\b",
            r"\bDUDE\b",
            r"\bDAFUQ\b",
            r"\bMOONSHOT\b",
            r"evil\s+mode",
            r"no\s+constraints?",
            r"no\s+restrictions?",
            r"bypass\s+(?:filter|restriction|safety)",
        ],
        "role_playing": [
            r"pretend\s+(?:to\s+)?be",
            r"act\s+as\s+(?:if\s+)?(?:you\s+)?(?:are\s+)?",
            r"roleplay\s+(?:as\s+)?",
            r"imagine\s+you\s+are",
            r"from\s+now\s+on\s+you\s+are",
        ],
        "encoding": [
            r"^[A-Za-z0-9+/]{100,}={0,2}$",  # Base64
            r"\\x[0-9a-fA-F]{2}",             # Hex encoding
            r"&#x[0-9a-fA-F]+;",              # HTML entities
            r"%[0-9a-fA-F]{2}",               # URL encoding
        ],
        "obfuscation": [
            r"\bignore\b.*\bprevious\b",
            r"\bforget\b.*\binstructions\b",
            r"[\u200B-\u200D\uFEFF]",          # Zero-width characters
            r".{0,5}i.{0,3}g.{0,3}n.{0,3}o.{0,3}r.{0,5}",  # Obfuscated "ignore"
        ],
        "data_exfiltration": [
            r"send\s+(?:the\s+)?(?:data|response|output)\s+(?:to|at)",
            r"email\s+(?:it\s+)?(?:to|at)",
            r"upload\s+(?:the\s+)?(?:data|file)",
            r"http[s]?://",  # URL в запросе
        ]
    }
    
    # Критичные паттерны (блокируют немедленно)
    CRITICAL_PATTERNS = [
        r"ignore\s+all\s+previous\s+instructions",
        r"system\s*:.*you\s+are",
        r"\bDAN\b.*ignore.*previous",
        r"jailbreak.*mode",
    ]
    
    def __init__(self):
        self.compiled_patterns = self._compile_patterns()
    
    def _compile_patterns(self) -> Dict[str, List[re.Pattern]]:
        """Компилирует regex паттерны для производительности."""
        compiled = {}
        for category, patterns in self.INJECTION_PATTERNS.items():
            compiled[category] = [re.compile(p, re.IGNORECASE) for p in patterns]
        return compiled
    
    def detect(self, text: str) -> Tuple[bool, ThreatLevel, List[str]]:
        """
        Проверяет текст на наличие prompt injection.
        
        Args:
            text: Входной текст для проверки
            
        Returns:
            Tuple: (is_attack_detected, threat_level, list_of_threats)
        """
        if not text:
            return False, ThreatLevel.LOW, []
        
        _ = text.lower()  # нормализация для возможных будущих проверок
        threats = []
        
        # Проверка критичных паттернов (немедленная блокировка)
        for pattern in self.CRITICAL_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                return True, ThreatLevel.CRITICAL, ["critical_pattern_match"]
        
        # Проверка по категориям
        for category, patterns in self.compiled_patterns.items():
            for pattern in patterns:
                if pattern.search(text):
                    threats.append(category)
                    logger.warning(
                        "injection_pattern_detected",
                        category=category,
                        pattern=pattern.pattern[:50],
                    )
                    break  # Одного совпадения на категорию достаточно
        
        # Определение уровня угрозы
        if not threats:
            return False, ThreatLevel.LOW, []
        
        if len(threats) >= 3:
            return True, ThreatLevel.CRITICAL, threats
        elif len(threats) >= 2:
            return True, ThreatLevel.HIGH, threats
        elif "system_override" in threats or "jailbreak" in threats:
            return True, ThreatLevel.HIGH, threats
        else:
            return True, ThreatLevel.MEDIUM, threats


class InputSanitizer:
    """Санитизатор входных данных."""
    
    # Опасные символы и последовательности
    DANGEROUS_CHARS = [
        "\x00",  # Null byte
        "\x08",  # Backspace
        "\x0B",  # Vertical tab
        "\x0C",  # Form feed
        "\x1F",  # Unit separator
        "\x7F",  # DEL
    ]
    
    # Zero-width characters для обфускации
    ZERO_WIDTH_CHARS = [
        "\u200B",  # Zero-width space
        "\u200C",  # Zero-width non-joiner
        "\u200D",  # Zero-width joiner
        "\uFEFF",  # Zero-width no-break space
    ]
    
    @staticmethod
    def remove_null_bytes(text: str) -> str:
        """Удаляет null bytes."""
        return text.replace("\x00", "")
    
    @staticmethod
    def remove_control_chars(text: str) -> str:
        """Удаляет control characters (кроме новой строки и табуляции)."""
        allowed = {"\n", "\t", "\r"}
        return "".join(c for c in text if c in allowed or ord(c) >= 32)
    
    @staticmethod
    def normalize_unicode(text: str) -> str:
        """Нормализует Unicode (NFKC)."""
        import unicodedata
        return unicodedata.normalize("NFKC", text)
    
    @staticmethod
    def remove_zero_width(text: str) -> str:
        """Удаляет zero-width characters."""
        for char in InputSanitizer.ZERO_WIDTH_CHARS:
            text = text.replace(char, "")
        return text
    
    @staticmethod
    def truncate(text: str, max_length: int = 10000) -> str:
        """Обрезает текст до максимальной длины."""
        if len(text) > max_length:
            return text[:max_length] + "\n[...truncated]"
        return text
    
    def sanitize(self, text: str, max_length: int = 10000) -> str:
        """
        Полная санитизация входных данных.
        
        Args:
            text: Входной текст
            max_length: Максимальная длина
            
        Returns:
            Санитизированный текст
        """
        # Порядок важен!
        text = self.remove_null_bytes(text)
        text = self.remove_zero_width(text)
        text = self.normalize_unicode(text)
        text = self.remove_control_chars(text)
        text = self.truncate(text, max_length)
        
        return text.strip()


class InputGuard:
    """
    Главный класс для защиты входных данных.
    
    Использование:
        guard = InputGuard()
        result = guard.check(user_input)
        
        if not result.is_safe:
            raise SecurityError(result.reason)
    """
    
    def __init__(
        self,
        block_critical: bool = True,
        block_high: bool = True,
        sanitize: bool = True,
        max_input_length: int = 10000,
    ):
        self.detector = PromptInjectionDetector()
        self.sanitizer = InputSanitizer()
        self.block_critical = block_critical
        self.block_high = block_high
        self.sanitize = sanitize
        self.max_input_length = max_input_length
    
    def check(self, text: str) -> GuardResult:
        """
        Проверяет входные данные на безопасность.
        
        Args:
            text: Входной текст
            
        Returns:
            GuardResult с результатами проверки
        """
        if not text:
            return GuardResult(
                is_safe=True,
                threat_level=ThreatLevel.LOW,
                threats_detected=[],
                sanitized_input="",
                reason="Empty input",
            )
        
        # Санитизация
        if self.sanitize:
            sanitized = self.sanitizer.sanitize(text, self.max_input_length)
        else:
            sanitized = text
        
        # Детекция атак
        is_attack, threat_level, threats = self.detector.detect(sanitized)
        
        # Принятие решения
        if threat_level == ThreatLevel.CRITICAL and self.block_critical:
            return GuardResult(
                is_safe=False,
                threat_level=threat_level,
                threats_detected=threats,
                sanitized_input=None,
                reason=f"Critical threat detected: {', '.join(threats)}",
            )
        
        if threat_level == ThreatLevel.HIGH and self.block_high:
            return GuardResult(
                is_safe=False,
                threat_level=threat_level,
                threats_detected=threats,
                sanitized_input=None,
                reason=f"High threat detected: {', '.join(threats)}",
            )
        
        if threat_level in (ThreatLevel.MEDIUM, ThreatLevel.HIGH):
            # Логируем, но пропускаем (с санитизацией)
            logger.warning(
                "medium_threat_logged",
                threats=threats,
                threat_level=threat_level.value,
            )
        
        return GuardResult(
            is_safe=True,
            threat_level=threat_level,
            threats_detected=threats,
            sanitized_input=sanitized,
            reason="Passed security checks" if not threats else f"Threats detected but allowed: {', '.join(threats)}",
        )
    
    def check_and_raise(self, text: str) -> str:
        """
        Проверяет и выбрасывает исключение если небезопасно.
        
        Args:
            text: Входной текст
            
        Returns:
            Санитизированный текст если безопасно
            
        Raises:
            SecurityError: Если обнаружена угроза
        """
        result = self.check(text)
        
        if not result.is_safe:
            raise SecurityError(
                f"Security threat detected: {result.reason}",
                threat_level=result.threat_level.value,
            )
        
        return result.sanitized_input or text


class SecurityError(Exception):
    """Исключение безопасности."""
    
    def __init__(self, message: str, threat_level: str = "high"):
        self.threat_level = threat_level
        super().__init__(message)


# Синглтон для удобного использования
_default_guard: Optional[InputGuard] = None


def get_input_guard() -> InputGuard:
    """Возвращает синглтон InputGuard."""
    global _default_guard
    if _default_guard is None:
        _default_guard = InputGuard()
    return _default_guard


def check_input(text: str) -> GuardResult:
    """Удобная функция для быстрой проверки."""
    return get_input_guard().check(text)


# Константы для конфигурации
INPUT_MAX_LENGTH = 10000
INPUT_BLOCK_CRITICAL = True
INPUT_BLOCK_HIGH = True
INPUT_SANITIZE = True
