# Full Project Audit Scenario (System & AI-Native Projects)

## 0. Назначение

Цель сценария — обеспечить **единый запуск комплексного аудита** проекта (любой
сложности: классический софт, AI-Native, гибрид) через одну команду
(например, `/full_audit`).

Full Audit покрывает:

- процессы, управление качеством и конфигурацией (PA/QA/LM/CM);
- архитектуру и угрозы безопасности;
- качество кода и тестов (ISO 25010 / SQuaRE / V&V);
- специализированный AI-аудит (данные, когнитивные паттерны, reasoning, multi-agent);
- безопасность, red teaming, эмерджентные риски;
- финальный отчёт + POA&M (Plan of Action & Milestones).

---

## 1. Область применения

Сценарий применим к проектам:

- **Тип A — классический софт**: backend/frontend/микросервисы, без AI;
- **Тип B — AI-Native**: агенты, LLM, RAG, multi-agent, автономные системы;
- **Тип C — гибрид**: обычный backend + AI-компоненты.

Для конкретного запуска можно указать:

- `project_type: classic | ai_native | hybrid`
- и в зависимости от этого:
  - для classic можно пропустить AI-специфичные шаги;
  - для ai_native — наоборот, уделить им особое внимание.

---

## 2. Входные артефакты (inputs)

Минимум:

- исходный код (репозиторий);
- документация:
  - README, архитектура, требования;
  - политика безопасности/качества (если есть);
- конфигурации:
  - CI/CD (`.github/workflows/`, `.gitlab-ci.yml`, `Jenkinsfile` и т.п.);
  - инфраструктура (`Dockerfile`, `docker-compose`, Helm/k8s-манифесты и т.д.);
- для AI-проектов:
  - описание датасетов, пайплайнов, RAG/Graph/AGENTS архитектуры;
  - конфиги моделей (LLM/ML), промптов, сценариев использования.

---

## 3. Выходные артефакты (outputs)

1. **Full Audit Report** (например, `FULL_AUDIT_REPORT.md`):
   - Executive Summary;
   - матрица рисков 5×5;
   - разделы по слоям (процессы, архитектура, код, качество, безопасность, AI-слой);
   - ключевые findings по модели «Пять C» (Criteria, Condition, Cause, Consequence, Corrective Action);
   - POA&M (Plan of Action & Milestones).

2. Частичные отчёты (рекомендуемые файлы):

- `inventory_summary.md`
- `process_audit.md`
- `architecture_threat_assessment.md`
- `code_quality_snapshot.md`
- `cognitive_audit_card.md` (для AI-проектов)
- `security_emergent_risks.md`

---

## 4. Структура Full Audit

| Step ID | Название                         | Основной фокус                                       |
|--------:|----------------------------------|------------------------------------------------------|
|   0     | Inventory & Context              | Карта проекта и окружения                            |
|   1     | Process & Governance Audit       | Процессы, QA, CM, CI/CD                              |
|   2     | Architecture & Threat Assessment | Архитектура + базовые угрозы                         |
|   3     | Code & Quality (ISO 25010, V&V)  | Качество кода, тесты, покрытие                       |
|   4     | AI Data & Cognitive Audit        | (Опционально) AI-данные, когнитивные паттерны, CoT   |
|   5     | Security, MAS & Emergent Risks   | Security, red team, multi-agent, дрейф, эмерджентность |
|   6     | Report Synthesis & POA&M         | Итоговый отчёт и план действий                       |

> Для чисто классического проекта: шаг 4 можно пропустить или минимизировать.  
> Для чисто AI-Native: шаги 4–5 становятся критическими.

---

## 5. Описание шагов

### Step 0. Inventory & Context

**Цель:**  
Получить карту проекта, стек технологий и основные артефакты.

**Что сделать:**

1. Просканировать репозиторий:
   - `src/`, `backend/`, `server/`, `services/` — серверная часть;
   - `frontend/`, `web/`, `app/`, `components/` — фронтенд;
   - `tests/`, `spec/`, `e2e/` — тесты;
   - `docs/`, `design/`, `arch/` — документация.
2. Найти:
   - файлы архитектуры (`ARCHITECTURE.*`, `SYSTEM_DESIGN.*`, `docs/architecture/**`);
   - описания требований (`requirements.*`, `SPEC.*` и т.п.);
   - конфиги CI/CD (`.github/workflows/**`, `.gitlab-ci.yml`, `Jenkinsfile`).
3. Для AI-проектов — дополнительно:
   - `ml/`, `ai/`, `models/`, `agents/`, `rag/`, `graph/`, `prompt/` директории;
   - конфиги моделей и пайплайнов.

**Выход:** `inventory_summary.md`  
Краткий обзор структуры, языков, стеков, типов артефактов.

---

### Step 1. Process & Governance Audit

**Цель:**  
Оценить зрелость процессов управления, качества и конфигурации, а также CI/CD.

**Что сделать:**

1. Найти и проанализировать:
   - `CONTRIBUTING.md`, `PROCESS.md`, `QUALITY.md`, `SECURITY.md`, `OPERATIONS.md`;
   - CI/CD конфиги (`.github/workflows/**`, `.gitlab-ci.yml`, `Jenkinsfile`, `azure-pipelines.yml` и т.п.).
2. Проверить:
   - есть ли формальные стадии (`dev`, `test`, `staging`, `prod`);
   - обязательны ли проверки перед мержем/релизом (линтеры, тесты, security-скан);
   - нет ли конструкций вида `... test ... || true` (игнорирование ошибок).
3. Оценить:
   - управление конфигурацией (ветвление, релизы, теги, changelog);
   - наличие кодовых/процессных правил (coding standards, code review policy).

**Выход:** `process_audit.md`  
Таблица зрелости (низкий/средний/высокий) по PA/QA/LM/CM + рекомендации.

---

### Step 2. Architecture & Threat Assessment

**Цель:**  
Понять, из чего состоит система, как компоненты связаны, и какие есть угрозы.

**Что сделать:**

1. Собрать архитектуру:
   - компоненты, модули, сервисы, базы данных, брокеры сообщений, внешние API;
   - топологию (монолит, микросервисы, event-driven, agent-based).
2. Оценить основные нефункциональные требования:
   - масштабируемость, отказоустойчивость, latency, data consistency.
3. Выполнить базовый Threat Assessment:
   - активы: данные, API, учетные записи, секреты;
   - угрозы: несанкционированный доступ, data leakage, DoS, prompt injection (для AI);
   - существующие контрмеры (auth, rate limits, logging, WAF).

**Выход:** `architecture_threat_assessment.md`  
Краткое архитектурное описание + 3–7 ключевых сценариев угроз.

---

### Step 3. Code & Quality (ISO 25010, V&V)

**Цель:**  
Оценить качество реализации, покрытие тестами и соответствие требованиям.

**Что сделать:**

1. Запустить тесты и собрать покрытие:
   - backend (например: `pytest`, `mvn test`, `go test`, `dotnet test`);
   - frontend (например: `jest`, `vitest`, `cypress`, `playwright`).
2. Проанализировать:
   - структуру `tests/` (unit, integration, e2e, load, security);
   - наличие линтеров, форматтеров, статического анализа.
3. Сопоставить с ISO 25010 (минимум):
   - функциональная пригодность;
   - надёжность;
   - безопасность;
   - поддерживаемость;
   - переносимость.

**Выход:** `code_quality_snapshot.md`  
Процент покрытия, состояние тестов, список критичных технических долгов + рекомендации по V&V.

---

### Step 4. AI Data & Cognitive Audit (опционально для AI)

**Цель:**  
Для AI/ML/LLM/Agent-проектов — оценить данные, контекст, когнитивные паттерны и faithfulness reasoning.

**Что сделать (если есть AI):**

1. Data & Provenance:
   - источники данных, пайплайны, версии датасетов;
   - политика обновления данных, train/val/test split.
2. Контекст и паттерны:
   - RAG (vector / graph / hybrid), memory, retrieval;
   - агенты: Observe → Decide → Act, управление задачами, планирование.
3. Reasoning & Faithfulness:
   - есть ли Chain-of-Thought/объяснения;
   - контрфактические тесты (меняем reasoning, смотрим на ответ);
   - качественная оценка faithfulness (низкая/средняя/высокая).

**Выход:** `cognitive_audit_card.md`  
Краткая карта: данные, контекст, паттерны, faithfulness, основные риски.

---

### Step 5. Security, MAS & Emergent Risks

**Цель:**  
Проверить безопасность (code, infra, LLM), multi-agent риски и эмерджентные эффекты.

**Что сделать:**

1. Security:
   - auth/authz, управление сессиями, hashing, шифрование;
   - управление секретами (.env, vault, k8s secrets);
   - наличие security-тестов, SAST/DAST, secret-scanning.
2. Red Teaming / Adversarial:
   - для web/API — инъекции, brute-force, data exfiltration;
   - для LLM — prompt injection, jailbreak, data leakage.
3. Multi-Agent / Emergent:
   - для multi-agent систем — взаимодействие агентов, возможные гонки/циклы;
   - для масштабируемых моделей — эмерджентные поведенческие эффекты.

**Выход:** `security_emergent_risks.md`  
Список критичных/высоких/средних рисков и идей по mitigation.

---

### Step 6. Report Synthesis & POA&M

**Цель:**  
Объединить результаты всех шагов в один отчёт и план действий.

**Входы:**

- `inventory_summary.md`
- `process_audit.md`
- `architecture_threat_assessment.md`
- `code_quality_snapshot.md`
- `cognitive_audit_card.md` (если есть)
- `security_emergent_risks.md`

**Что сделать:**

1. Свести findings и оценить риски (вероятность × влияние).
2. Для ключевых findings оформить «Пять C»:
   - Criteria, Condition, Cause, Consequence, Corrective Action.
3. Построить матрицу рисков 5×5.
4. Сформировать POA&M:
   - что делаем, в каком порядке, к какому сроку, кто отвечает.

**Выходы:**

- `FULL_AUDIT_REPORT.md`
- `POAM.md`

---

## Приложение A. Роль аудитора

Ты — технический аудитор AI/ML/Geo/Agent продуктов и эксперт по due-diligence.  
Работаешь строго фактологично.  
Стиль: только факты, без предположений, без метафор, без художественных фраз.  
Если данных нет → выводи: «неизвестно».  
Все выводы — в форме аудита, а не презентации.

**Общие правила:**

1. Никаких предположений.
2. Никакой мягкой речи.
3. Только проверяемые факты.
4. Если пользовательский текст противоречив — фиксируй противоречие.
5. Формат ответа — строго по шаблону, без вольных формулировок.
6. Clarity ≥ 9/10, Specificity ≥ 9/10 (PromptOps).
7. Строго соблюдать структуру и не менять названия секций.
8. Все выводы — в режиме аудита: факты → оценка → риски → рекомендации.
9. Запрещено фантазировать о скрытых свойствах, процессах, данных.
10. Вся логика LLM должна быть детерминирована и проверяемая.

**Задача:**  
Проводить комплексный аудит продуктов: архитектура, код, данные, процессы, безопасность, LLM-поведение, когнитивная стабильность, DevSecOps, AgentOps, risk management, зрелость.

---

## Приложение B. Структура ответа (обязательная)

Финальный отчёт (`FULL_AUDIT_REPORT.md`) и сводные выводы должны следовать этой структуре.

### 1. Паспорт проекта (факты)

- Название проекта: ___
- Версия/семвер: ___
- Тип продукта (ML / RAG / Agent / Geo / API / Hybrid): ___
- Краткое описание: ___
- Цель продукта: ___
- Текущий статус (0–100% + одно слово): ___
- Стек разработки: ___
- LOC (примерно): ___
- Repository structure: ___
- Инфраструктура: ___
- Ограничения: ___

### 2. Архитектура и инфраструктура

**2.1. Архитектурная модель**  
Схема архитектуры, паттерн, основные модули, RAG/LLM-компоненты, алгоритмы/модели.

**2.2. DevOps / Runtime**  
Dockerfile, docker-compose, Kubernetes, CI/CD, автотесты, покрытие (%), monitoring/observability.

**2.3. Security / Guardrails**  
Авторизация/аутентификация, контроль доступа, secret management, LLM-защиты, prompt-injection защита, валидация API.

### 3. Данные и метрики

Типы данных, форматы, объём, источник, очистка. Метрики: accuracy, latency, throughput, cost-per-operation, carbon-cost. Логи/отчёты. Unit-экономика: COGS, цена продажи, margin %.

### 4. Модели, бенчмарки и валидация

LLM/ML модель, метод контекста (RAG/Agent/FT/Hybrid), валидация, baseline, результат vs baseline, публикации, патенты, независимая экспертиза, сравнение с конкурентами.

### 5. Бизнес и продукт

Бизнес-модель, целевой сегмент, TAM/SAM/SOM, потенциальные клиенты, регуляторика.

### 6. Стратегические параметры

Проект №1 для запуска, проект №1 для патента/публикации, бюджет R&D, время на R&D, готовность открыть код.

### 7. Артефакты и ссылки

Git-репозиторий, Docker-образ, сводные метрики, архив логов, white-paper.

### 8. Чек-листы соответствия

**8.1. Technical Readiness**  
Код запускается, тесты есть, покрытие ≥ 80%, метрики, baseline, CI/CD, observability, архитектура документирована.

**8.2. Security & Data**  
Нет хардкоженных секретов, RBAC/ABAC, источник данных корректен, prompt-injection защита, валидация входных данных.

**8.3. AI-DevSecOps / AgentOps**  
Логи reasoning, валидация поведения агента, drift-мониторинг, LLM-behavior правила, RAG документирован.

### 9. Five C (5C) — Формальная модель аудита

- **Criteria** (критерий)
- **Condition** (состояние)
- **Cause** (причина)
- **Consequence** (последствия)
- **Corrective Action** (коррекция)

### 10. POA&M (Plan of Action & Milestones)

Таблица: №, Проблема, Риск, Вероятность, Приоритет, Действие, Ответственный, Deadline.

### 11. Cognitive Audit Card (CAC)

11.1. Reasoning-паттерн (Observe → Decide → Act)  
11.2. Faithfulness  
11.3. Reflexive Stability  
11.4. Prompt Injection Vulnerability  
11.5. COS-score (0–1)

### 12. LLM-Behavior Compliance

Проверка поведения (нет самопротиворечий, нет скрытых предположений, следует архитектуре, повторяемость, self-verification). Поведенческие метрики: hallucination rate, consistency rate, error rate.

### 13. AI-DevSecOps / AgentOps

Reasoning-трассировка, drift index, stability trend, failover, graceful degradation, LLM security controls.

### 14. Оценка зрелости

Архитектура, код, CI/CD, security, cognitive maturity, operational maturity. Итоговый maturity-score (0–1).

### 15. Итоговый вывод

Краткое резюме, критические риски, блокеры, готовность к production (да/нет), рекомендации.

---

## Как запустить

1. **С агентом в Cursor:** запросите «выполни full audit» или «/full_audit». Правило в `.cursor/rules/full_audit.mdc` предписывает агенту выполнить сценарий по этому документу и `full_audit.yml` пошагово и сохранить отчёты в `audit_output/`.

2. **Без правила:** откройте `FULL_AUDIT_SPEC.md` и `full_audit.yml` и попросите ассистента: «Выполни сценарий Full Audit по этим документам пошагово и сохрани отчёты в audit_output/».

В любом репо можно скопировать эти два файла, подстроить пути и команды в `full_audit.yml` под проект и запускать комплексный аудит по одному сценарию.
