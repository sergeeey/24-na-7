# 🔒 Security Policy — Reflexio 24/7

**Политика безопасности и обработка уязвимостей**

---

## 🛡️ Модель угроз

### Угрозы и митигации

| Угроза | Описание | Митигация |
|--------|----------|-----------|
| **PII утечка** | Персональные данные в логах/выводах | SAFE PII masking, Zero-retention аудио |
| **Секреты в коде** | API ключи в репозитории | `.env` в `.gitignore`, Secret management |
| **SQL Injection** | Внедрение SQL кода | Pydantic валидация, параметризованные запросы |
| **API перегрузка** | DDoS атаки | Rate limiting, SAFE payload validation |
| **Несанкционированный доступ** | Доступ к API без авторизации | RLS политики в Supabase, Domain allowlist |

### Trust Boundaries и Data Flow

**Edge / Android**
- Локальная очередь сегментов, foreground recording, store-and-forward.
- Основные риски: потеря сегментов, повторная отправка, локальный доступ к устройству.

**Public API / FastAPI ingress**
- HTTP и WebSocket ingress для ingest/admin/query paths.
- Основные риски: отсутствие Bearer auth, upload abuse, oversized payloads, rate-limit bypass.

**Processing / Memory Pipeline**
- ASR → episode → truth gate → digest.
- Основные риски: ложная память из шумного ASR, speculative digest claims, тихая деградация quality layer.

**Persistent Storage**
- SQLite, digest cache, episodic memory, transition logs.
- Основные риски: несогласованность truth-state и digest cache, опасные destructive admin actions, утечка PII в артефактах.

### Abuse Cases v1

- auth bypass на protected endpoints
- destructive misuse `POST /admin/reset-all` и `POST /admin/reclassify`
- malformed / non-WAV / oversized ingest payloads
- false-memory pollution через garbage/duplicate transcripts
- overclaiming digest under fragmented or degraded context

---

## 🔐 Работа с секретами

### Переменные окружения

**ВАЖНО:** Все секреты хранятся в `.env`, который **НЕ коммитится** в Git.

```bash
# .env файл (уже в .gitignore)
BRAVE_API_KEY=...
BRIGHTDATA_API_KEY=...
OPENAI_API_KEY=...
SUPABASE_SERVICE_ROLE=...  # ⚠️ ОПАСНО! Только на сервере
```

### Проверка секретов в коде

```bash
# Проверка на утечку секретов
python .cursor/validation/safe/run.py --mode strict
grep -r "api.*key\|password\|token" --exclude-dir=venv --exclude-dir=.git .
```

### Ротация ключей

**Рекомендуется:** Ротация ключей каждые 90 дней

1. Обновить ключи в `.env`
2. Проверить: `python scripts/smoke_llm.py` (для LLM)
3. Проверить: `@playbook validate-mcp` (для MCP)

---

## 🔍 PII (Personally Identifiable Information)

### Политика маскирования

SAFE автоматически маскирует:
- Email адреса → `[EMAIL_REDACTED]`
- Телефоны → `[PHONE_REDACTED]`
- Банковские карты → `[CARD_REDACTED]`
- IP адреса → `[IP_REDACTED]`

### Включение PII маскирования

```bash
# В .env
SAFE_PII_MASK=1
SAFE_MODE=strict
```

### Проверка PII

```bash
# Проверка на PII в текстах
python - <<'PYCODE'
from .cursor.validation.safe.checks import SAFEChecker
checker = SAFEChecker()
has_pii, detected, masked = checker.check_pii_in_text("Contact: john@example.com or +7 999 123-45-67")
print(f"PII detected: {has_pii}, Types: {detected}")
print(f"Masked: {masked}")
PYCODE
```

---

## 🚫 Zero-Retention Policy

### Аудио файлы

- Аудио удаляется **сразу после транскрипции**
- Хранятся только текстовые транскрипции
- Максимальное время хранения: **24 часа**

### Настройка

```python
# В коде (src/api/main.py)
EDGE_DELETE_AFTER_UPLOAD = True  # Удаление после загрузки
```

---

## 🌐 Domain Allowlist

### Разрешённые домены

Настроено в `.cursor/validation/safe/policies.yaml`:

```yaml
domain_allowlist:
  allowed:
    - "api.search.brave.com"
    - "api.brightdata.com"
    - "*.supabase.co"
    - "api.openai.com"
    - "api.anthropic.com"
```

### Добавление нового домена

1. Обновить `policies.yaml`
2. Перезапустить API: `docker compose restart api`

---

## 🔒 Supabase Security

### Row Level Security (RLS)

**ВАЖНО:** Включите RLS для всех таблиц в Supabase Dashboard!

```sql
-- Пример политики (в Supabase SQL Editor)
ALTER TABLE transcriptions ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Enable read access for service role"
ON transcriptions FOR SELECT
TO service_role
USING (true);
```

### Service Role Key

- ⚠️ **НИКОГДА** не используйте в браузере!
- ✅ Только на сервере
- ✅ Только для административных задач

---

## 🧪 Security Testing

### Регулярные проверки

```bash
# Еженедельно
@playbook security-validate

# SAFE проверки
python .cursor/validation/safe/run.py --mode strict

# Проверка зависимостей (если используется)
pip audit  # или safety check
```

### Penetration Testing

Рекомендуется внешний аудит безопасности перед production deploy.

### Negative Test Contract

Минимальный обязательный негативный набор:
- protected endpoint без Bearer token -> `401`
- protected endpoint с неверным Bearer token -> `401`
- destructive admin endpoint без explicit confirm -> `400`
- `POST /admin/reclassify` в режиме `dry_run` не меняет truth-state
- ingest invalid payloads отклоняются до normal memory path

---

## 📋 Compliance

### GDPR

- Zero-retention аудио ✅
- PII маскирование ✅
- Право на удаление данных ✅ (через API)

### SOC 2 (планируется)

- Логирование доступа
- Audit trails
- Инцидент-менеджмент

---

## 🚨 Reporting Security Issues

Если обнаружена уязвимость:

1. **НЕ создавайте публичный issue**
2. Отправьте email на: security@reflexio.example.com
3. Включите:
   - Описание уязвимости
   - Шаги воспроизведения
   - Предложенное исправление (если есть)

**Время ответа:** В течение 48 часов

---

**Последнее обновление:** 3 ноября 2025











