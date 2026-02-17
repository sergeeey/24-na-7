"""Конфигурация приложения."""
from pathlib import Path
from typing import Dict
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Настройки приложения."""
    
    # API
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000
    API_URL: str = "http://localhost:8000"
    
    # Storage
    STORAGE_PATH: Path = Path("src/storage")
    UPLOADS_PATH: Path = Path("src/storage/uploads")
    RECORDINGS_PATH: Path = Path("src/storage/recordings")
    
    # Audio
    AUDIO_SAMPLE_RATE: int = 16000
    AUDIO_FRAME_MS: int = 30
    AUDIO_SILENCE_LIMIT: float = 2.0  # секунды
    AUDIO_VAD_AGGRESSIVENESS: int = 2  # 0-3
    
    # ASR
    ASR_MODEL_SIZE: str = "small"
    ASR_DEVICE: str = "cpu"
    ASR_COMPUTE_TYPE: str = "int8"
    
    # Edge
    EDGE_ENABLED: bool = True
    EDGE_AUTO_UPLOAD: bool = True
    EDGE_DELETE_AFTER_UPLOAD: bool = True
    
    # Speech Filter
    FILTER_MUSIC: bool = False  # Включить фильтрацию музыки/шума
    FILTER_METHOD: str = "energy"  # "energy", "none"
    FILTER_SPEECH_BAND_LOW: int = 300  # Нижняя граница речевого диапазона (Гц)
    FILTER_SPEECH_BAND_HIGH: int = 3400  # Верхняя граница речевого диапазона (Гц)
    FILTER_ENERGY_THRESHOLD: float = 0.4  # Порог доли энергии в речевом диапазоне
    FILTER_HIGH_FREQ_THRESHOLD: float = 0.3  # Порог доли энергии выше 4 кГц (музыка)
    
    # Extended Metrics
    EXTENDED_METRICS: bool = False  # Включить расширенные когнитивные метрики
    USE_LLM_METRICS: bool = False  # Использовать LLM для анализа (будущая функция)
    
    # MCP Intelligence (Brave Search & Bright Data)
    BRAVE_API_KEY: str | None = None
    BRIGHTDATA_API_KEY: str | None = None
    BRIGHTDATA_PROXY_HTTP: str | None = None  # HTTP proxy endpoint
    BRIGHTDATA_PROXY_WS: str | None = None  # WebSocket proxy endpoint
    BRIGHTDATA_ZONE: str = "serp_api1"  # Зона по умолчанию для SERP API
    BRIGHTDATA_ZONES: Dict[str, str] = {}  # Словарь зон для разных типов миссий
    
    # Supabase
    SUPABASE_URL: str | None = None  # URL проекта Supabase
    SUPABASE_ANON_KEY: str | None = None  # Anon/public ключ (безопасен для браузера)
    SUPABASE_SERVICE_KEY: str | None = None  # Service ключ (для обхода RLS, только на сервере)
    
    # LLM Providers
    LLM_PROVIDER: str = "openai"  # openai | anthropic
    OPENAI_API_KEY: str | None = None
    ANTHROPIC_API_KEY: str | None = None
    LLM_MODEL_ACTOR: str = "gpt-4o-mini"
    LLM_MODEL_CRITIC: str = "gpt-4o-mini"
    LLM_TEMPERATURE_ACTOR: float = 0.3
    LLM_TEMPERATURE_CRITIC: float = 0.0
    
    # SAFE / Security
    SAFE_MODE: str = "audit"  # strict | audit | disabled
    SAFE_PII_MASK: bool = True
    
    # Database
    DB_BACKEND: str = "sqlite"  # sqlite | supabase
    
    # Logging
    LOG_LEVEL: str = "INFO"
    
    # Rate Limiting (P0-2 Security)
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_STORAGE: str = "memory"  # memory | redis
    REDIS_URL: str | None = None  # redis://localhost:6379/0
    RATE_LIMIT_INGEST: str = "10/minute"
    RATE_LIMIT_TRANSCRIBE: str = "30/minute"
    RATE_LIMIT_DIGEST: str = "60/minute"
    RATE_LIMIT_HEALTH: str = "200/minute"
    RATE_LIMIT_DEFAULT: str = "100/minute"
    
    # Vault Configuration (P0-3 Security)
    VAULT_ENABLED: bool = False  # Включить для production
    VAULT_ADDR: str = "http://localhost:8200"
    VAULT_TOKEN: str | None = None
    VAULT_NAMESPACE: str | None = None
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True


# Глобальный экземпляр настроек
settings = Settings()

# Создаём директории при импорте
settings.STORAGE_PATH.mkdir(parents=True, exist_ok=True)
settings.UPLOADS_PATH.mkdir(parents=True, exist_ok=True)
settings.RECORDINGS_PATH.mkdir(parents=True, exist_ok=True)


# Lazy import для Vault (чтобы не замедлять старт)
def _get_secret_from_vault(key: str, env_fallback: str | None) -> str | None:
    """Получает secret из Vault с fallback на env."""
    if settings.VAULT_ENABLED:
        try:
            from src.utils.vault_client import get_secret
            vault_value = get_secret(key)
            if vault_value:
                return vault_value
        except Exception:
            pass  # Fallback на env
    return env_fallback


# Property getters для API ключей с поддержкой Vault
@property
def openai_api_key() -> str | None:
    return _get_secret_from_vault("openai", settings.OPENAI_API_KEY)

@property
def anthropic_api_key() -> str | None:
    return _get_secret_from_vault("anthropic", settings.ANTHROPIC_API_KEY)

@property
def supabase_service_key() -> str | None:
    return _get_secret_from_vault("supabase_service", settings.SUPABASE_SERVICE_KEY)

@property
def brave_api_key() -> str | None:
    return _get_secret_from_vault("brave", settings.BRAVE_API_KEY)

@property
def brightdata_api_key() -> str | None:
    return _get_secret_from_vault("brightdata", settings.BRIGHTDATA_API_KEY)

