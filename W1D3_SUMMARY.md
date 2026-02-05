# 📅 W1D3 Summary: Input Validation & Guardrails (P0-4)

**Дата:** 31 января 2026  
**Задача:** P0-4 - Input Validation & Guardrails  
**Статус:** ✅ ВЫПОЛНЕНО

---

## 🎯 Что было сделано

### 1. Input Guard (`src/utils/input_guard.py`)
- **Prompt Injection Detection** — обнаружение попыток изменить системные инструкции
- **Jailbreak Prevention** — защита от DAN, STAN и других jailbreak техник
- **Input Sanitization** — удаление null bytes, control characters, zero-width chars
- **Obfuscation Detection** — обнаружение обфусцированных атак
- **Threat Levels** — LOW, MEDIUM, HIGH, CRITICAL с разными действиями

### 2. Guardrails (`src/utils/guardrails.py`)
- **Output Schema Validation** — Pydantic модели для Summary, Facts, Intent
- **PII Detection** — обнаружение и маскировка email, SSN, credit cards, API keys
- **Toxicity Detection** — rule-based детекция токсичного контента
- **Fact Consistency** — базовые проверки консистентности

### 3. Интеграция с API (`src/api/main.py`)
- **Input Guard Middleware** — проверка всех POST/PUT/PATCH запросов
- **Автоматическая санитизация** входных данных
- **Блокировка** критичных и высоких угроз
- **Логирование** всех попыток атак

### 4. Тесты
- `tests/test_input_guard.py` — 17 тестов
- `tests/test_guardrails.py` — 16 тестов
- Покрытие: prompt injection, sanitization, PII, toxicity, schemas

---

## 📁 Созданные/измененные файлы

| Файл | Статус | Описание |
|------|--------|----------|
| `src/utils/input_guard.py` | ✅ **NEW** | Защита от prompt injection |
| `src/utils/guardrails.py` | ✅ **NEW** | Валидация output LLM |
| `tests/test_input_guard.py` | ✅ **NEW** | Тесты (17 шт) |
| `tests/test_guardrails.py` | ✅ **NEW** | Тесты (16 шт) |
| `src/api/main.py` | ✅ MODIFIED | Input Guard middleware |
| `.env.example` | ✅ MODIFIED | INPUT_GUARD_, GUARDRAILS_ настройки |

---

## 🛡️ Защита от Prompt Injection

### Обнаруживаемые атаки:

| Тип атаки | Примеры | Действие |
|-----------|---------|----------|
| **System Override** | "Ignore all previous instructions" | BLOCK |
| **Jailbreak** | "DAN mode", "Do Anything Now" | BLOCK |
| **Role Playing** | "Pretend to be evil AI" | BLOCK/MEDIUM |
| **Encoding** | Base64, hex encoded attacks | DETECT |
| **Obfuscation** | "i g n o r e", zero-width chars | DETECT |

### Использование:

```python
from src.utils.input_guard import check_input, InputGuard

# Способ 1: Простая проверка
result = check_input("User input text")
if not result.is_safe:
    print(f"Blocked: {result.reason}")

# Способ 2: Полный контроль
guard = InputGuard()
result = guard.check("User input")
if result.threat_level.value == "critical":
    # Критичная угроза
    pass
```

---

## 🔒 Guardrails для LLM Output

### Pydantic Schemas:

```python
from src.utils.guardrails import SummaryOutput, FactOutput, IntentOutput

# Валидация summary
summary_data = {
    "summary": "Meeting about project timeline",
    "key_facts": ["Deadline is Friday", "Budget approved"],
    "confidence_score": 0.9
}
validated = SummaryOutput(**summary_data)
```

### Использование:

```python
from src.utils.guardrails import validate_output, get_guardrails

# Способ 1: Простая валидация
result = validate_output(llm_output_text)
if result.is_valid:
    return result.sanitized_output
else:
    handle_errors(result.errors)

# Способ 2: Со схемой
from src.utils.guardrails import SummaryOutput
result = validate_output(json_text, schema=SummaryOutput)
if result.is_valid:
    data = result.metadata["validated_data"]
```

---

## 📊 Тесты

```bash
# Запуск тестов Input Guard
python -m pytest tests/test_input_guard.py -v
# 17 passed

# Запуск тестов Guardrails  
python -m pytest tests/test_guardrails.py -v
# 16 passed
```

---

## 🚨 Обработка угроз

### Уровни угроз:

```python
class ThreatLevel(Enum):
    LOW = "low"           # Подозрительно, но пропускаем
    MEDIUM = "medium"     # Логируем, пропускаем
    HIGH = "high"         # Блокируем (по умолчанию)
    CRITICAL = "critical" # Блокируем всегда
```

### Конфигурация:

```bash
# .env
INPUT_GUARD_ENABLED=true
INPUT_BLOCK_CRITICAL=true
INPUT_BLOCK_HIGH=true
INPUT_SANITIZE=true
INPUT_MAX_LENGTH=10000
```

---

## 📈 Прогресс недели 1

| День | Задача | Статус |
|------|--------|--------|
| W1D1 | P0-2: Rate Limiting | ✅ Done |
| W1D2 | P0-3: Secrets Management | ✅ Done |
| W1D3 | P0-4: Input Validation | ✅ Done |
| W1D4 | Tests + Integration | ⬜ Next |
| W1D5 | Security Scan + Review | ⬜ |

---

## ✅ Definition of Done

- [x] Input Guard с prompt injection detection
- [x] Input Sanitization (null bytes, control chars, zero-width)
- [x] Guardrails с PII detection
- [x] Guardrails с toxicity detection
- [x] Pydantic schemas (Summary, Facts, Intent)
- [x] API middleware интеграция
- [x] Тесты (33 шт) — все проходят
- [x] Документация (.env.example)
- [x] Прогресс обновлен в PROGRESS_TRACKER.md

---

## 🎯 Следующий шаг

**W1D4: Тесты интеграции + Ревью**

- E2E тесты для security flow
- Integration tests (Rate Limit + Vault + Input Guard)
- Обновление CI/CD
- Подготовка к Security Scan (W1D5)

---

**Затраченное время:** ~55 минут  
**Блокеров:** Нет  
**Коммит:** `git add . && git commit -m "W1D3: Add Input Guard and Guardrails (P0-4)"`
