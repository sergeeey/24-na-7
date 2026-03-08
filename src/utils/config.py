"""Конфигурация приложения."""
from pathlib import Path
from typing import Dict

from pydantic import ConfigDict
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Настройки приложения."""

    # API
    API_HOST: str = "0.0.0.0"  # nosec B104 — intentional: Docker container exposes only mapped ports
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

    # ASR (единый источник для локального faster-whisper; приоритет над config/asr.yaml и env)
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
    LLM_TIMEOUT_SEC: float = 120.0  # таймаут вызова API (дайджест, CoD, extract_tasks)

    # SAFE / Security
    SAFE_MODE: str = "audit"
    SAFE_PII_MASK: bool = True

    # Database
    DB_BACKEND: str = "sqlite"

    # Timezone — offset пользователя от UTC (Алматы = +6)
    # ПОЧЕМУ не pytz/zoneinfo: один пользователь, одна таймзона, offset достаточен.
    # Используется для конвертации "дня пользователя" в UTC-диапазон при выборке из БД.
    USER_TZ_OFFSET: int = 6

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
    # ПОЧЕМУ 0.003: телефонный микрофон (Pixel 9 Pro) даёт RMS=0.005-0.007 для нормальной речи.
    # Старое значение 0.01 отфильтровывало 100% записей. 0.003 пропускает речь, но режет тишину.
    SPEAKER_AMPLITUDE_THRESHOLD: float = 0.003  # RMS gate: ~-50dBFS (телефонный микрофон)
    # ПОЧЕМУ 0.65: короткие VAD-сегменты (0.3-1.7с) дают similarity 0.65-0.76.
    # Старое значение 0.75 отфильтровывало ~60% легитимных записей.
    SPEAKER_SIMILARITY_THRESHOLD: float = 0.65  # Cosine similarity cutoff (relaxed for phone mic)
    SPEAKER_MIN_ENROLLMENT_SAMPLES: int = 3      # Минимум образцов для профиля

    # Audio Retention (единая политика для API и edge listener)
    # ПОЧЕМУ: в production — zero-retention (0). При тестировании — 48h для диагностики.
    AUDIO_RETENTION_HOURS: int = 0  # 0 = удалять сразу после транскрипции

    @property
    def WAV_CLEANUP_MAX_AGE_HOURS(self) -> int:
        """Возраст (часы) для очистки WAV при старте listener. Не менее 1ч при zero-retention (PII)."""
        return max(1, self.AUDIO_RETENTION_HOURS)

    # Rate Limiting
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_STORAGE: str = "memory"
    REDIS_URL: str | None = None
    RATE_LIMIT_INGEST: str = "10/minute"
    RATE_LIMIT_TRANSCRIBE: str = "30/minute"
    RATE_LIMIT_DIGEST: str = "60/minute"
    RATE_LIMIT_HEALTH: str = "200/minute"
    RATE_LIMIT_DEFAULT: str = "100/minute"

    # SQLCipher — шифрование БД
    SQLCIPHER_KEY: str | None = None

    # Embeddings
    ENABLE_LOCAL_EMBEDDINGS: bool = False
    EMBEDDING_DIM: int = 1536  # 1536 для OpenAI text-embedding-3-small, 384 для MiniLM

    # Ingest
    INGEST_SYNC_PROCESS: bool = False

    # Hugging Face (pyannote.audio diarization)
    HF_TOKEN: str | None = None

    # Google AI (Gemini — каскадный LLM fallback)
    GOOGLE_API_KEY: str | None = None
    LLM_CASCADE_ORDER: str = "google,anthropic,openai"

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

    model_config = ConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
    )


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


