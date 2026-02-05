# 🛡️ Неделя 1: Security Hardening — План работы

**Даты:** 03.02.2026 — 09.02.2026  
**Цель:** Закрыть все P0-блокираторы по безопасности  
**Ответственный:** Tech Lead / DevOps

---

## 📋 Чеклист недели

### День 1-2: Rate Limiting (P0-2)

#### Задача 1.1: Установка slowapi
```bash
# Добавить в requirements.txt
slowapi>=0.1.9

# Или установить
pip install slowapi
```

#### Задача 1.2: Интеграция с FastAPI
```python
# src/api/main.py - добавить:
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

# Создать limiter
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Применить к endpoint'ам:
@app.post("/ingest/audio")
@limiter.limit("10/minute")  # 10 uploads per minute
async def ingest_audio(request: Request, file: UploadFile = File(...)):
    ...
```

#### Задача 1.3: Настройка лимитов
```python
# src/utils/config.py - добавить:
class Settings(BaseSettings):
    # ... existing ...
    
    # Rate Limiting
    RATE_LIMIT_INGEST: str = "10/minute"
    RATE_LIMIT_TRANSCRIBE: str = "30/minute"
    RATE_LIMIT_DIGEST: str = "60/minute"
    RATE_LIMIT_DEFAULT: str = "100/minute"
```

#### Задача 1.4: Тестирование
```python
# tests/test_rate_limiting.py
import pytest
from fastapi.testclient import TestClient
from src.api.main import app

def test_rate_limit_ingest():
    client = TestClient(app)
    
    # Отправить 11 запросов
    for i in range(11):
        response = client.post("/ingest/audio", files={"file": ("test.wav", b"fake", "audio/wav")})
    
    # 11-й должен вернуть 429
    assert response.status_code == 429
    assert "rate limit" in response.json()["detail"].lower()
```

- [ ] Установлен slowapi
- [ ] Лимиты настроены для всех endpoints
- [ ] Тесты проходят
- [ ] Документация обновлена

---

### День 3-4: Secrets Management (P0-3)

#### Задача 2.1: Выбор решения
**Вариант A: HashiCorp Vault (Self-hosted)**
```bash
# Docker Compose добавить:
vault:
  image: hashicorp/vault:latest
  container_name: reflexio-vault
  ports:
    - "8200:8200"
  environment:
    - VAULT_DEV_ROOT_TOKEN_ID=root
  volumes:
    - vault-data:/vault/file
```

**Вариант B: AWS Secrets Manager (Cloud)**
```python
# src/utils/secrets.py
import boto3
from botocore.exceptions import ClientError

class SecretsManager:
    def __init__(self):
        self.client = boto3.client('secretsmanager')
    
    def get_secret(self, secret_name):
        try:
            response = self.client.get_secret_value(SecretId=secret_name)
            return response['SecretString']
        except ClientError as e:
            raise e
```

#### Задача 2.2: Миграция ключей
```bash
# Скрипт миграции: scripts/migrate_secrets.py
#!/usr/bin/env python3
"""Миграция secrets из .env в Vault."""

import os
import hvac  # Vault client
from dotenv import load_dotenv

load_dotenv()

client = hvac.Client(url='http://localhost:8200', token='root')

secrets = {
    'openai': os.getenv('OPENAI_API_KEY'),
    'anthropic': os.getenv('ANTHROPIC_API_KEY'),
    'supabase': os.getenv('SUPABASE_SERVICE_KEY'),
    'brave': os.getenv('BRAVE_API_KEY'),
    'brightdata': os.getenv('BRIGHTDATA_API_KEY'),
}

for key, value in secrets.items():
    if value:
        client.secrets.kv.v2.create_or_update_secret(
            path=f'reflexio/{key}',
            secret=dict(api_key=value)
        )
        print(f"✓ Migrated: {key}")
```

#### Задача 2.3: Обновление Settings
```python
# src/utils/config.py - обновить:
from src.utils.secrets import SecretsManager

class Settings(BaseSettings):
    # ...
    
    # Secrets Manager
    SECRETS_BACKEND: str = "vault"  # vault | aws | env
    VAULT_URL: str | None = None
    VAULT_TOKEN: str | None = None
    
    @property
    def openai_api_key(self):
        if self.SECRETS_BACKEND == "vault":
            return SecretsManager().get_secret("reflexio/openai")
        return self.OPENAI_API_KEY
```

- [ ] Vault развернут
- [ ] Secrets мигрированы
- [ ] Код обновлен
- [ ] .env удален из репозитория

---

### День 5-7: Input Validation & Guardrails (P0-4)

#### Задача 3.1: Установка Guardrails
```bash
pip install guardrails-ai
```

#### Задача 3.2: Создание валидаторов
```python
# src/llm/guardrails.py
from guardrails import Guard
from guardrails.hub import RegexMatch, ToxicLanguage
import pydantic

# Валидация выхода LLM
class SummaryOutput(pydantic.BaseModel):
    summary: str
    confidence_score: float
    key_facts: list[str]

summary_guard = Guard.for_pydantic(SummaryOutput)

# Проверка на токсичность
toxic_guard = Guard().use(ToxicLanguage, threshold=0.5, on_fail="exception")

# Проверка на PII
pii_guard = Guard().use(
    RegexMatch,
    regex=r"\b\d{3}-\d{2}-\d{4}\b",  # SSN pattern
    on_fail="exception"
)
```

#### Задача 3.3: Интеграция с LLM
```python
# src/llm/providers.py - обновить:
from src.llm.guardrails import summary_guard, toxic_guard

class OpenAIClient(LLMClient):
    def call(self, prompt: str, ...):
        # ... существующий код ...
        
        # Применить Guardrails
        try:
            validated = toxic_guard.validate(response_text)
            return {"text": validated, ...}
        except Exception as e:
            logger.error("toxic_content_detected", error=str(e))
            return {"text": "", "error": "Content blocked by safety filters"}
```

#### Задача 3.4: Prompt Injection Protection
```python
# src/api/middleware.py
import re

PROMPT_INJECTION_PATTERNS = [
    r"ignore previous instructions",
    r"system prompt",
    r"you are now",
    r"DAN",
    r"jailbreak",
]

def detect_prompt_injection(text: str) -> bool:
    text_lower = text.lower()
    for pattern in PROMPT_INJECTION_PATTERNS:
        if re.search(pattern, text_lower):
            return True
    return False

# В SAFE middleware:
if detect_prompt_injection(body.get("text", "")):
    return JSONResponse(
        status_code=400,
        content={"error": "Potential prompt injection detected"}
    )
```

- [ ] Guardrails установлены
- [ ] Валидаторы созданы
- [ ] Prompt injection protection активен
- [ ] Тесты проходят

---

## 📊 Метрики успеха

| Метрика | До | После | Цель |
|---------|-----|-------|------|
| Security Score | 5.5/10 | | 8.0/10 |
| Bandit Critical | ? | | 0 |
| Bandit High | ? | | 0 |
| P0 Closed | 0/6 | | 3/6 |

---

## 🎯 Definition of Done

- [ ] Rate limiting работает на всех endpoints
- [ ] Secrets хранятся в Vault (не в .env)
- [ ] Guardrails блокируют токсичный контент
- [ ] Prompt injection защита активна
- [ ] Security scan (Bandit) = 0 critical/high
- [ ] Документация обновлена
- [ ] PR создан и ревью пройден

---

## 🚨 Escalation

При блокерах > 4 часов:
1. Зафиксировать проблему в GitHub Issues
2. Уведомить команды в Telegram
3. Приоритизировать с Product Owner

---

**Начало работ:** 03.02.2026  
**Конец недели:** 09.02.2026  
**Ревью:** 10.02.2026
