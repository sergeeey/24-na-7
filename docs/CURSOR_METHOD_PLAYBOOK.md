# CURSOR_METHOD_PLAYBOOK.md

**Версия:** 1.0  
**Дата:** 4 ноября 2025  
**Проект:** Reflexio 24/7

---

## TL;DR

Reflexio 24/7 — AI-Native система для пассивной записи речи и анализа. Cursor используется для разработки, аудита, генерации кода и документации. Проект использует Memory Bank, Playbooks Suite, Governance Loop, CEB-E аудит. Работа через playbooks (`@playbook`), правила в `.cursor/rules/`, контекст в `.cursor/memory/`. Критично: два мира API ключей (Python `.env` и MCP Cursor Settings). Не использовать Agent Mode и Reasoning в Cursor — данных о таких ограничениях в проекте нет, но рекомендуется работать через playbooks и правила.

---

## 1. Контекст проекта

### Тип проекта

**AI-Native система** для пассивной записи речи, транскрипции и анализа:
- Edge-запись с VAD (Voice Activity Detection)
- ASR транскрипция (faster-whisper, Whisper API)
- LLM анализ и генерация дайджестов
- OSINT Knowledge Discovery System
- Supabase PostgreSQL storage
- Production Level 5 (Self-Adaptive)

**Архитектура:** Модульный монолит (Modulith) на FastAPI + Python 3.11+

### Роль Cursor в проекте

1. **Разработка кода:** Генерация и рефакторинг Python-кода
2. **Аудит системы:** CEB-E стандарт (9 компонентов, 100 баллов)
3. **Документация:** Генерация и обновление MD-файлов
4. **Автоматизация:** Playbooks для стандартных задач
5. **Валидация:** SAFE+CoVe проверки безопасности
6. **Управление:** Governance Loop для профилей системы

**Источники контекста:**
- `.cursor/memory/` — Memory Bank (projectbrief.md, decisions.md, systemPatterns.md, roadmap.md)
- `.cursor/rules/` — Правила поведения (base_rules.yaml, reflexio-patterns.md)
- `.cursor/playbooks/` — 18 готовых playbooks
- `.cursor/governance/` — Профили управления (profile.yaml)

---

## 2. Модель взаимодействия «Человек ↔ Cursor»

### Режимы работы

**Основной режим:** Playbooks через `@playbook` команду

**Доступные playbooks:**
- `@playbook audit-standard` — CEB-E аудит
- `@playbook build-reflexio` — полная сборка
- `@playbook init` — инициализация проекта
- `@playbook prod-readiness` — проверка готовности к продакшену
- `@playbook validate-mcp` — проверка MCP сервисов
- `@playbook osint-mission` — запуск OSINT миссии
- И ещё 12 playbooks (см. `.cursor/playbooks/`)

**Inline edits:** Стандартные правки кода через Cursor

**Ask режим:** Для вопросов о проекте, архитектуре, паттернах

### Конфигурация Cursor

**Memory Bank:** Автоматически используется из `.cursor/memory/`

**Rules Engine:** Правила из `.cursor/rules/` активируются автоматически

**MCP Gateway:** Настроен в `.cursor/mcp.json` (Brave Search, BrightData, Reflexio API)

**Governance:** Профиль в `.cursor/governance/profile.yaml` (текущий: production, Level 5)

**⚠️ Критично — два мира API ключей:**

1. **Python-приложение:** Ключи в `.env` (корень проекта)
   - Читает: Python код (`src/utils/config.py`)
   - Формат: `OPENAI_API_KEY=sk-...` (без кавычек, без пробелов)

2. **MCP-серверы Cursor:** Ключи в Cursor Settings → MCP
   - Читает: Cursor Editor (НЕ читает `.env` проекта!)
   - Настройка: Settings → MCP → Configure → добавить переменные
   - Перезагрузка: `Cmd/Ctrl + Shift + P` → `Developer: Reload Window`

**Подробнее:** `API_KEYS_SETUP.md`

### Границы — что Cursor НЕ должен делать

**Данных недостаточно** о явных ограничениях Agent Mode или Reasoning в проекте. Однако:

- **Рекомендуется:** Работать через playbooks и правила, а не через свободный Agent Mode
- **Не рекомендуется:** Прямые изменения в `.cursor/governance/profile.yaml` без аудита
- **Запрещено:** Коммитить `.env` файлы (см. `.cursor/rules/base_rules.yaml`)

---

## 3. Паттерны и исторические находки

### Подходы, применяемые в проекте

1. **Audit-driven development:**
   - CEB-E стандарт (9 компонентов, 100 баллов)
   - Автоматический аудит через `@playbook audit-standard`
   - Governance Loop применяет результаты аудита

2. **Playbook-first:**
   - Все стандартные задачи через playbooks
   - 18 готовых playbooks в `.cursor/playbooks/`
   - Параметры через `--param key=value`

3. **Memory Bank автообновление:**
   - Контекст в `.cursor/memory/` обновляется при архитектурных изменениях
   - Используется автоматически Cursor IDE

4. **Self-measured система:**
   - Автоматическое измерение метрик из тестов
   - Обновление чеклистов через `scripts/auto_measure.py`
   - Валидация через `scripts/validate_checklist.py`

### Best Practices (что доказано работает)

1. **Использование playbooks:**
   - ✅ `@playbook build-reflexio` для полной сборки
   - ✅ `@playbook audit-standard` для проверки зрелости
   - ✅ `@playbook validate-mcp` для проверки MCP сервисов

2. **Правила в `.cursor/rules/`:**
   - ✅ `base_rules.yaml` — базовые правила (trigger: always)
   - ✅ `reflexio-patterns.md` — архитектурные паттерны (trigger: on_pattern_match)

3. **Memory Bank структура:**
   - ✅ `projectbrief.md` — описание проекта
   - ✅ `decisions.md` — ADR (Architectural Decision Records)
   - ✅ `systemPatterns.md` — паттерны разработки
   - ✅ `roadmap.md` — план развития

4. **CEB-E аудит:**
   - ✅ Запуск через `@playbook audit-standard`
   - ✅ Результаты в `.cursor/audit/audit_report.md`
   - ✅ Governance Loop применяет профиль автоматически

5. **Два мира API ключей:**
   - ✅ Python: `.env` в корне проекта
   - ✅ MCP: Cursor Settings → MCP
   - ✅ Проверка: `python scripts/check_api_keys.py`

**Ссылки на файлы:**
- `.cursor/rules/base_rules.yaml` — правила
- `.cursor/playbooks/audit.yaml` — пример playbook
- `API_KEYS_SETUP.md` — настройка ключей
- `docs/CHECKLIST_AUDIT_FIXES.md` — примеры валидации

### Anti-Patterns (что ломалось и почему)

1. **Путаница с API ключами:**
   - ❌ Попытка использовать `.env` для MCP серверов
   - ❌ Кавычки/пробелы в `.env` (формат: `KEY=value`, без кавычек)
   - ✅ Решение: Чёткое разделение двух миров (см. `API_KEYS_SETUP.md`)

2. **Ручное изменение Governance:**
   - ❌ Прямое редактирование `.cursor/governance/profile.yaml` без аудита
   - ✅ Решение: Использовать `@playbook audit-standard` → Governance Loop применяет автоматически

3. **Игнорирование правил:**
   - ❌ Изменения без обновления Memory Bank
   - ✅ Решение: Обновлять `.cursor/memory/` при архитектурных изменениях

4. **Отсутствие валидации:**
   - ❌ Изменения чеклистов без валидации
   - ✅ Решение: `python scripts/validate_checklist.py --checklist <file>`

**Ссылки на файлы:**
- `API_KEYS_SETUP.md` — раздел "Частые ошибки"
- `docs/CHECKLIST_AUDIT_FIXES.md` — примеры исправлений

---

## 4. Методология работы с проектами этого типа

### Шаг 0 — Подготовка Cursor

**Настройка правил:**
- Правила автоматически загружаются из `.cursor/rules/`
- Проверка: Убедиться, что `base_rules.yaml` и `reflexio-patterns.md` существуют

**Настройка Memory Bank:**
- Контекст автоматически загружается из `.cursor/memory/`
- Проверка: Убедиться, что файлы актуальны (projectbrief.md, decisions.md, systemPatterns.md)

**Настройка MCP:**
- Проверка: `@playbook validate-mcp-config`
- Если ошибки: Настроить ключи в Cursor Settings → MCP (см. `API_KEYS_SETUP.md`)

**⚠️ Данных недостаточно** о необходимости отключения Agent Mode или Reasoning. Рекомендуется работать через playbooks.

### Шаг 1 — Первичная ориентация

**Файлы для открытия:**
1. `README.md` — общее описание проекта
2. `docs/Project.md` — архитектура и компоненты
3. `.cursor/memory/projectbrief.md` — миссия и цели
4. `.cursor/memory/decisions.md` — архитектурные решения (ADR)
5. `.cursor/governance/profile.yaml` — текущий профиль системы

**Вопросы для Cursor:**
- "Какова архитектура проекта Reflexio 24/7?"
- "Какие playbooks доступны в проекте?"
- "Как настроены API ключи для Python и MCP?"
- "Какой текущий уровень зрелости системы (CEB-E)?"

### Шаг 2 — Настройка правил под проект

**Правила уже настроены:**
- `.cursor/rules/base_rules.yaml` — базовые правила (trigger: always)
- `.cursor/rules/reflexio-patterns.md` — паттерны (trigger: on_pattern_match)

**Обновление правил:**
- При изменении архитектуры обновить `reflexio-patterns.md`
- При изменении процессов обновить `base_rules.yaml`

**Проверка правил:**
- Cursor автоматически применяет правила
- Ручная проверка: Прочитать файлы в `.cursor/rules/`

### Шаг 3 — Основные сценарии работы

#### Сценарий 1: Аудит проекта

```bash
# Запуск CEB-E аудита
@playbook audit-standard

# Результаты:
# - .cursor/audit/audit_report.md
# - .cursor/audit/audit_report.json
# - Governance Loop применяет профиль автоматически
```

**Что проверяется:**
- 9 компонентов CEB-E (Rules, Memory, MCP, Hooks, Validation, Observability, Governance, Playbooks, Multi-Agent)
- Методологическое соответствие (Predictive Analytics, UQ, DQ, XAI, RAG, Closed-Loop Learning)
- Оценка зрелости (0-100 баллов, Level 0-5)

**Ссылки:**
- `.cursor/audit/CEB-E_STANDARD.md` — стандарт
- `.cursor/audit/README.md` — инструкция

#### Сценарий 2: Самодиагностика Cursor

**Данных недостаточно** о явной самодиагностике Cursor. Однако:

**Проверка Memory Bank:**
- Убедиться, что файлы в `.cursor/memory/` актуальны
- Обновить при архитектурных изменениях

**Проверка правил:**
- Убедиться, что правила в `.cursor/rules/` соответствуют проекту

**Проверка MCP:**
```bash
@playbook validate-mcp
```

#### Сценарий 3: Диагностика моделей/ключей

```bash
# Проверка API ключей (оба мира)
python scripts/check_api_keys.py

# Проверка MCP конфигурации
@playbook validate-mcp-config

# Проверка доступности MCP сервисов
@playbook validate-mcp

# Проверка прокси (BrightData)
@playbook proxy-diagnostics

# Проверка SERP (Brave Search)
@playbook serp-diagnostics
```

**Ссылки:**
- `API_KEYS_SETUP.md` — полная инструкция
- `.cursor/audit/proxy_diagnostics.md` — результаты диагностики

#### Сценарий 4: Работа с кодом без Agent Mode

**Рекомендуемый подход:**
- Использовать playbooks для стандартных задач
- Использовать inline edits для правок кода
- Использовать Ask режим для вопросов

**Примеры:**
```bash
# Сборка проекта
@playbook build-reflexio

# Инициализация
@playbook init

# Проверка готовности к продакшену
@playbook prod-readiness
```

**⚠️ Данных недостаточно** о явных ограничениях Agent Mode. Рекомендуется работать через playbooks.

### Шаг 4 — Контроль качества

**Проверки правильного поведения Cursor:**

1. **Правила применяются:**
   - Cursor следует правилам из `.cursor/rules/`
   - Проверка: Cursor предлагает решения согласно правилам

2. **Memory Bank используется:**
   - Cursor понимает контекст проекта
   - Проверка: Cursor ссылается на файлы из `.cursor/memory/`

3. **Playbooks работают:**
   - Playbooks выполняются без ошибок
   - Проверка: `@playbook audit-standard` завершается успешно

4. **MCP сервисы доступны:**
   - MCP серверы зелёные в Cursor
   - Проверка: `@playbook validate-mcp`

**Конкретные проверки:**

```bash
# Аудит системы
@playbook audit-standard

# Валидация чеклиста
python scripts/validate_checklist.py --checklist .cursor/tasks/surpass_smart_noter_checklist.yaml

# Проверка метрик
make audit-checklist
```

### Шаг 5 — Фиксация опыта

**Что обновлять:**

1. **Playbook (`docs/CURSOR_METHOD_PLAYBOOK.md`):**
   - Добавить новые паттерны
   - Добавить анти-паттерны
   - Обновить промпт-шаблоны

2. **Правила (`.cursor/rules/`):**
   - Обновить `base_rules.yaml` при изменении процессов
   - Обновить `reflexio-patterns.md` при изменении архитектуры

3. **Memory Bank (`.cursor/memory/`):**
   - Обновить `decisions.md` при новых ADR
   - Обновить `systemPatterns.md` при новых паттернах
   - Обновить `projectbrief.md` при изменении миссии

4. **Документация (`docs/`):**
   - Обновить `Changelog.md` при изменениях
   - Обновить `Project.md` при архитектурных изменениях

---

## 5. Устойчивые промпт-шаблоны

### Группа 1: Диагностика

#### Шаблон 1.1: Проверка готовности системы

**Текст:**
```
Проверь готовность системы Reflexio 24/7 к работе:
1. Проверь наличие всех необходимых файлов (.env, .cursor/mcp.json)
2. Проверь доступность MCP сервисов
3. Проверь текущий профиль Governance
4. Выведи краткий отчёт о состоянии системы
```

**Когда применять:** При первом запуске проекта или после длительного перерыва

**Что НЕ должен делать:** Не изменять конфигурацию без явного запроса

---

#### Шаблон 1.2: Диагностика API ключей

**Текст:**
```
Проверь настройку API ключей для Reflexio 24/7:
1. Проверь наличие .env файла в корне проекта
2. Проверь структуру .cursor/mcp.json
3. Объясни разницу между двумя мирами ключей (Python и MCP)
4. Укажи, где настраивать ключи для каждого мира
```

**Когда применять:** При ошибках аутентификации или недоступности сервисов

**Что НЕ должен делать:** Не показывать реальные значения ключей (только структуру)

---

### Группа 2: Аудит

#### Шаблон 2.1: Запуск CEB-E аудита

**Текст:**
```
Запусти CEB-E аудит системы Reflexio 24/7:
1. Выполни @playbook audit-standard
2. Проанализируй результаты аудита
3. Укажи компоненты с низкими баллами
4. Предложи конкретные шаги для улучшения
```

**Когда применять:** Перед релизом, после значительных изменений, по расписанию

**Что НЕ должен делать:** Не изменять Governance профиль вручную (только через Governance Loop)

---

#### Шаблон 2.2: Проверка методологического соответствия

**Текст:**
```
Проверь методологическое соответствие проекта Reflexio 24/7:
1. Проверь соответствие стандартам (Predictive Analytics, UQ, DQ, XAI, RAG, Closed-Loop Learning)
2. Укажи области несоответствия
3. Предложи план исправления
```

**Когда применять:** При обновлении методологии или перед аудитом

**Что НЕ должен делать:** Не изменять код без явного запроса

---

### Группа 3: Настройка Cursor

#### Шаблон 3.1: Настройка Memory Bank

**Текст:**
```
Обнови Memory Bank для проекта Reflexio 24/7:
1. Проверь актуальность файлов в .cursor/memory/
2. Укажи, какие файлы нужно обновить
3. Предложи структуру обновлений
```

**Когда применять:** После архитектурных изменений, при добавлении новых ADR

**Что НЕ должен делать:** Не удалять существующие файлы без явного запроса

---

#### Шаблон 3.2: Настройка MCP сервисов

**Текст:**
```
Настрой MCP сервисы для проекта Reflexio 24/7:
1. Проверь структуру .cursor/mcp.json
2. Укажи, какие сервисы нужно включить
3. Объясни, где настраивать ключи (Cursor Settings → MCP)
4. Предложи команды для проверки доступности
```

**Когда применять:** При первом запуске, при добавлении новых MCP сервисов

**Что НЕ должен делать:** Не изменять .cursor/mcp.json без явного запроса

---

### Группа 4: Работа с кодом/анализ

#### Шаблон 4.1: Анализ архитектуры модуля

**Текст:**
```
Проанализируй архитектуру модуля [название] в проекте Reflexio 24/7:
1. Опиши структуру модуля
2. Укажи зависимости и связи с другими модулями
3. Проверь соответствие паттернам из .cursor/rules/reflexio-patterns.md
4. Предложи улучшения (если есть)
```

**Когда применять:** При работе с новым модулем, при рефакторинге

**Что НЕ должен делать:** Не изменять код без явного запроса

---

#### Шаблон 4.2: Генерация кода по паттернам

**Текст:**
```
Сгенерируй код для [описание] в проекте Reflexio 24/7:
1. Следуй паттернам из .cursor/rules/reflexio-patterns.md
2. Используй structlog для логирования
3. Используй Result-паттерн для обработки ошибок
4. Добавь Pydantic модели для валидации
5. Следуй модульной структуре (≤500 строк на модуль)
```

**Когда применять:** При создании нового функционала

**Что НЕ должен делать:** Не нарушать существующие паттерны, не создавать зависимости без необходимости

---

## 6. Анти-паттерны и грабли

### Анти-паттерн 1: Путаница с API ключами

**Где происходит:** Настройка MCP сервисов

**Почему:** MCP серверы Cursor НЕ читают `.env` файл проекта

**Как распознать:**
- MCP серверы красные в Cursor
- Ошибки "missing API key" в MCP логах
- Cursor не может использовать MCP функции

**Безопасный обходной путь:**
1. Настроить ключи в Cursor Settings → MCP
2. Перезагрузить окно: `Cmd/Ctrl + Shift + P` → `Developer: Reload Window`
3. Проверить: `@playbook validate-mcp`

**Ссылки:** `API_KEYS_SETUP.md` — раздел "Мир 2: MCP-серверы Cursor"

---

### Анти-паттерн 2: Ручное изменение Governance

**Где происходит:** `.cursor/governance/profile.yaml`

**Почему:** Governance Loop должен применять профиль автоматически на основе аудита

**Как распознать:**
- Профиль не соответствует результатам аудита
- Профиль изменён вручную без аудита
- Governance Loop не применяет изменения

**Безопасный обходной путь:**
1. Запустить аудит: `@playbook audit-standard`
2. Дождаться применения Governance Loop автоматически
3. Если нужно принудительно: `python .cursor/metrics/governance_loop.py --apply results`

**Ссылки:** `.cursor/governance/README.md`

---

### Анти-паттерн 3: Игнорирование правил

**Где происходит:** При изменении архитектуры или процессов

**Почему:** Правила в `.cursor/rules/` не обновляются, Cursor работает с устаревшим контекстом

**Как распознать:**
- Cursor предлагает решения, не соответствующие текущей архитектуре
- Cursor не следует паттернам из `reflexio-patterns.md`
- Memory Bank содержит устаревшую информацию

**Безопасный обходной путь:**
1. Обновить `.cursor/rules/reflexio-patterns.md` при изменении архитектуры
2. Обновить `.cursor/memory/` при значительных изменениях
3. Перезагрузить контекст Cursor (переоткрыть проект)

**Ссылки:** `.cursor/rules/base_rules.yaml`, `.cursor/memory/README.md`

---

### Анти-паттерн 4: Отсутствие валидации чеклистов

**Где происходит:** При изменении чеклистов (`.cursor/tasks/*.yaml`)

**Почему:** Чеклисты могут содержать несоответствия (даты, количество задач, метрики)

**Как распознать:**
- Несоответствие дат в чеклисте
- Неправильное количество задач
- Метрики с `current: null` без обоснования

**Безопасный обходной путь:**
1. Валидировать чеклист: `python scripts/validate_checklist.py --checklist <file>`
2. Автоматическое исправление: `python scripts/validate_checklist.py --checklist <file> --fix`
3. Создать снапшот: `python scripts/snapshot_checklist.py`

**Ссылки:** `docs/CHECKLIST_AUDIT_FIXES.md`

---

### Анти-паттерн 5: Кавычки/пробелы в .env

**Где происходит:** Файл `.env` в корне проекта

**Почему:** Python `python-dotenv` не обрабатывает кавычки и пробелы вокруг `=`

**Как распознать:**
- Переменные окружения не загружаются (`None` в коде)
- Ошибки "environment variable not set"
- Проверка: `python -c "from src.utils.config import settings; print(settings)"` показывает `None`

**Безопасный обходной путь:**
1. Формат: `KEY=value` (без кавычек, без пробелов)
2. Проверка: `python scripts/check_api_keys.py`
3. Пример правильного формата: `API_KEYS_SETUP.md` — раздел "Правила оформления .env"

**Ссылки:** `API_KEYS_SETUP.md` — раздел "Правила оформления .env"

---

## 7. Рекомендации «на будущее я»

### Что избегать в первую очередь

1. **Путаница с API ключами:**
   - Не пытаться использовать `.env` для MCP серверов
   - Всегда помнить о двух мирах ключей

2. **Ручное изменение Governance:**
   - Не редактировать `.cursor/governance/profile.yaml` вручную
   - Всегда использовать аудит → Governance Loop

3. **Игнорирование правил:**
   - Не забывать обновлять `.cursor/rules/` и `.cursor/memory/`
   - Всегда следовать паттернам из `reflexio-patterns.md`

4. **Отсутствие валидации:**
   - Не изменять чеклисты без валидации
   - Всегда использовать `scripts/validate_checklist.py`

### Что делать в новом проекте первым делом

1. **Изучить структуру:**
   - Прочитать `README.md` и `docs/Project.md`
   - Изучить `.cursor/memory/projectbrief.md`
   - Понять архитектуру через `.cursor/memory/decisions.md`

2. **Настроить API ключи:**
   - Создать `.env` для Python-приложения
   - Настроить MCP сервисы в Cursor Settings
   - Проверить: `python scripts/check_api_keys.py`

3. **Запустить аудит:**
   - `@playbook audit-standard`
   - Изучить результаты в `.cursor/audit/audit_report.md`
   - Понять текущий уровень зрелости

4. **Изучить playbooks:**
   - Просмотреть доступные playbooks: `.cursor/playbooks/`
   - Попробовать основные: `@playbook build-reflexio`, `@playbook validate-mcp`

### Где смотреть, если Cursor ведёт себя странно

1. **Проверка правил:**
   - Убедиться, что правила в `.cursor/rules/` актуальны
   - Проверить, что Cursor применяет правила

2. **Проверка Memory Bank:**
   - Убедиться, что файлы в `.cursor/memory/` актуальны
   - Обновить при необходимости

3. **Проверка MCP:**
   - `@playbook validate-mcp`
   - Проверить логи: `View → Output → MCP Logs`

4. **Проверка Governance:**
   - Изучить `.cursor/governance/profile.yaml`
   - Запустить аудит: `@playbook audit-standard`

5. **Проверка API ключей:**
   - `python scripts/check_api_keys.py`
   - Проверить `.env` и Cursor Settings → MCP

---

## Золотые правила (5–7 пунктов)

1. **Всегда используй playbooks для стандартных задач:**
   - `@playbook audit-standard` для аудита
   - `@playbook build-reflexio` для сборки
   - `@playbook validate-mcp` для проверки MCP

2. **Помни о двух мирах API ключей:**
   - Python: `.env` в корне проекта
   - MCP: Cursor Settings → MCP (НЕ читает `.env`!)

3. **Не изменяй Governance вручную:**
   - Всегда через аудит → Governance Loop
   - Профиль применяется автоматически

4. **Обновляй Memory Bank при изменениях:**
   - `.cursor/memory/decisions.md` при новых ADR
   - `.cursor/memory/systemPatterns.md` при новых паттернах
   - `.cursor/rules/reflexio-patterns.md` при изменении архитектуры

5. **Валидируй чеклисты перед коммитом:**
   - `python scripts/validate_checklist.py --checklist <file>`
   - Автоматическое исправление: `--fix`

6. **Следуй паттернам проекта:**
   - Модульная структура (≤500 строк на модуль)
   - structlog для логирования
   - Result-паттерн для ошибок
   - Pydantic для валидации

7. **Используй CEB-E аудит для оценки зрелости:**
   - Запускай регулярно: `@playbook audit-standard`
   - Изучай результаты и улучшай слабые компоненты
   - Доверяй Governance Loop для применения профиля

---

## Приложение: Отсутствующие данные

### Что не найдено в проекте

1. **Safe Profile для Cursor:**
   - Данных недостаточно о явной настройке Safe Profile
   - Рекомендуется работать через playbooks и правила

2. **Отключение Agent Mode:**
   - Данных недостаточно о явных ограничениях Agent Mode
   - Рекомендуется работать через playbooks

3. **Отключение Reasoning:**
   - Данных недостаточно о явных ограничениях Reasoning
   - Reasoning упоминается в контексте LLM (не Cursor)

4. **Самодиагностика Cursor:**
   - Данных недостаточно о явной самодиагностике Cursor
   - Рекомендуется проверять Memory Bank, правила, MCP вручную

5. **Явные границы Agent Mode:**
   - Данных недостаточно о том, что Cursor НЕ должен делать в Agent Mode
   - Рекомендуется работать через playbooks и правила

### Где искать дополнительную информацию

1. **Документация проекта:**
   - `README.md` — общее описание
   - `docs/Project.md` — архитектура
   - `docs/Changelog.md` — история изменений

2. **Memory Bank:**
   - `.cursor/memory/projectbrief.md` — миссия
   - `.cursor/memory/decisions.md` — ADR
   - `.cursor/memory/systemPatterns.md` — паттерны

3. **Правила:**
   - `.cursor/rules/base_rules.yaml` — базовые правила
   - `.cursor/rules/reflexio-patterns.md` — паттерны

4. **Аудит:**
   - `.cursor/audit/CEB-E_STANDARD.md` — стандарт
   - `.cursor/audit/README.md` — инструкция
   - `AUDIT_REPORT_PRESENTATION.md` — пример отчёта

---

**Последнее обновление:** 4 ноября 2025  
**Версия:** 1.0  
**Статус:** ✅ Готов к использованию


