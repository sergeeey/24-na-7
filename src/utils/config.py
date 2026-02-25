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
    AUDIO_SILENCE_LIMIT: float = 2.0
    AUDIO_VAD_AGGRESSIVENESS: int = 2

    # ASR
    ASR_MODEL_SIZE: str = "small"
    ASR_DEVICE: str = "auto"
    ASR_COMPUTE_TYPE: str = "auto"
    ASR_LANGUAGE: str | None = None

    # Edge
    EDGE_ENABLED: bool = True
    EDGE_AUTO_UPLOAD: bool = True
    EDGE_DELETE_AFTER_UPLOAD: bool = True

    # Speech Filter
    FILTER_MUSIC: bool = False
    FILTER_METHOD: str = "energy"
    FILTER_SPEECH_BAND_LOW: int = 300
    FILTER_SPEECH_BAND_HIGH: int = 3400
    FILTER_ENERGY_THRESHOLD: float = 0.4
    FILTER_HIGH_FREQ_THRESHOLD: float = 0.3

    # Extended Metrics
    EXTENDED_METRICS: bool = False
    USE_LLM_METRICS: bool = False

    # Privacy/Memory/Integrity feature flags
    PRIVACY_MODE: str = "audit"  # strict | mask | audit
    MEMORY_ENABLED: bool = True
    RETRIEVAL_ENABLED: bool = True
    INTEGRITY_CHAIN_ENABLED: bool = True

    # MCP Intelligence
    BRAVE_API_KEY: str | None = None
    BRIGHTDATA_API_KEY: str | None = None
    BRIGHTDATA_PROXY_HTTP: str | None = None
    BRIGHTDATA_PROXY_WS: str | None = None
    BRIGHTDATA_ZONE: str = "serp_api1"
    BRIGHTDATA_ZONES: Dict[str, str] = {}

    # Supabase
    SUPABASE_URL: str | None = None
    SUPABASE_ANON_KEY: str | None = None
    SUPABASE_SERVICE_KEY: str | None = None

    # LLM Providers
    LLM_PROVIDER: str = "openai"
    OPENAI_API_KEY: str | None = None
    ANTHROPIC_API_KEY: str | None = None
    LLM_MODEL_ACTOR: str = "gpt-4o-mini"
    LLM_MODEL_CRITIC: str = "gpt-4o-mini"
    LLM_TEMPERATURE_ACTOR: float = 0.3
    LLM_TEMPERATURE_CRITIC: float = 0.0

    # SAFE / Security
    SAFE_MODE: str = "audit"
    SAFE_PII_MASK: bool = True

    # Database
    DB_BACKEND: str = "sqlite"

    # Logging
    LOG_LEVEL: str = "INFO"

    # Authentication
    API_KEY: str | None = None

    # CORS — comma-separated list of allowed origins
    CORS_ORIGINS: str = "http://localhost:3000,http://localhost:8080"

    # Speaker Verification
    # ПОЧЕМУ disabled по умолчанию: backward compatible — не ломает существующих пользователей.
    # Включить после создания голосового профиля (POST /voice/enroll).
    SPEAKER_VERIFICATION_ENABLED: bool = False
    SPEAKER_AMPLITUDE_THRESHOLD: float = 0.01  # RMS gate: ~-40dBFS
    SPEAKER_SIMILARITY_THRESHOLD: float = 0.75  # Cosine similarity cutoff
    SPEAKER_MIN_ENROLLMENT_SAMPLES: int = 3      # Минимум образцов для профиля

    # Rate Limiting
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_STORAGE: str = "memory"
    REDIS_URL: str | None = None
    RATE_LIMIT_INGEST: str = "10/minute"
    RATE_LIMIT_TRANSCRIBE: str = "30/minute"
    RATE_LIMIT_DIGEST: str = "60/minute"
    RATE_LIMIT_HEALTH: str = "200/minute"
    RATE_LIMIT_DEFAULT: str = "100/minute"

    # Vault Configuration
    VAULT_ENABLED: bool = False
    VAULT_ADDR: str = "http://localhost:8200"
    VAULT_TOKEN: str | None = None
    VAULT_NAMESPACE: str | None = None

    @property
    def openai_api_key(self) -> str | None:
        return _get_secret_from_vault(self, "openai", self.OPENAI_API_KEY)

    @property
    def anthropic_api_key(self) -> str | None:
        return _get_secret_from_vault(self, "anthropic", self.ANTHROPIC_API_KEY)

    @property
    def supabase_service_key(self) -> str | None:
        return _get_secret_from_vault(self, "supabase_service", self.SUPABASE_SERVICE_KEY)

    @property
    def brave_api_key(self) -> str | None:
        return _get_secret_from_vault(self, "brave", self.BRAVE_API_KEY)

    @property
    def brightdata_api_key(self) -> str | None:
        return _get_secret_from_vault(self, "brightdata", self.BRIGHTDATA_API_KEY)

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True


settings = Settings()

settings.STORAGE_PATH.mkdir(parents=True, exist_ok=True)
settings.UPLOADS_PATH.mkdir(parents=True, exist_ok=True)
settings.RECORDINGS_PATH.mkdir(parents=True, exist_ok=True)


def _get_secret_from_vault(cfg: Settings, key: str, env_fallback: str | None) -> str | None:
    """Получает secret из Vault с fallback на env."""
    if cfg.VAULT_ENABLED:
        try:
            from src.utils.vault_client import get_secret

            vault_value = get_secret(key)
            if vault_value:
                return vault_value
        except Exception:
            pass
    return env_fallback


