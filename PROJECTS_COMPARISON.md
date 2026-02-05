# Отчет о сравнении проектов

**Дата:** 2026-02-05 18:28:53 UTC

**Проект 1:** `golos` (C:\Users\serge\Desktop\golos)
**Проект 2:** `24 na 7` (D:\24 na 7)

---

## Общая сводка

- **Всего файлов в golos:** 30
- **Всего файлов в 24 na 7:** 439
- **Уникальных для golos:** 25
- **Уникальных для 24 na 7:** 434
- **Пересекающихся файлов:** 5

## Рекомендация по слиянию

**Рекомендуемая база:** 24 na 7
**Уверенность:** Средняя

- Оценка golos: 30/100
- Оценка 24 na 7: 70/100

**Обоснование:**
- Проект 1 имеет 4 более свежих файлов против 1 в проекте 2
- Проект 2 имеет 434 уникальных файлов против 25 в проекте 1
- Проект 2 имеет 17 уникальных зависимостей против 12 в проекте 1

## Анализ времени модификации файлов

- **Пересекающихся файлов:** 5
- **Новее в golos:** 4
- **Новее в 24 na 7:** 1
- **Одинаковое время:** 0

## Анализ полноты файлов

- **Всего файлов в golos:** 30
- **Всего файлов в 24 na 7:** 439
- **Уникальных для golos:** 25
- **Уникальных для 24 na 7:** 434

## Анализ зависимостей

### Python (requirements.txt)

- **Всего в golos:** 20 пакетов
- **Всего в 24 na 7:** 25 пакетов
- **Общих зависимостей:** 0
- **Конфликтов версий:** 8
- **Уникальных для golos:** 12
- **Уникальных для 24 na 7:** 17

#### Конфликтующие Python зависимости

| Пакет | Версия в проекте 1 | Версия в проекте 2 |
|-------|-------------------|-------------------|
| fastapi | ==0.104.1 | >=0.110.0 |
| numpy | ==1.26.2 | >=1.26.0 |
| pydantic | ==2.5.0 | >=2.0.0 |
| pydantic-settings | ==2.1.0 | >=2.0.0 |
| python-dotenv | ==1.0.0 | >=1.0.0 |
| sounddevice | ==0.4.6 | >=0.4.6 |
| uvicorn[standard] | ==0.24.0 | >=0.29.0 |
| webrtcvad | ==2.0.10 | >=2.0.10 |

## Уникальные файлы

### Уникальные для golos

**.md** (11 файлов):

- `.cursor\memory_bank\activeContext.md`
- `.cursor\memory_bank\decisions.md`
- `.cursor\memory_bank\progress.md`
- `.cursor\memory_bank\projectbrief.md`
- `.cursor\memory_bank\systemPatterns.md`
- `AUTONOMY_CONFIG.md`
- `AUTO_CLAUDE_START.md`
- `CLAUDE.md`
- `MODEL_STRATEGY.md`
- `PRELOADED_CONTEXT.md`
- *...и ещё 1 файлов*

**.mdc** (3 файлов):

- `.cursor\rules\00-general.mdc`
- `.cursor\rules\05-security.mdc`
- `.cursor\rules\20-testing.mdc`

**.ps1** (3 файлов):

- `scripts\download_models.ps1`
- `scripts\install_service.ps1`
- `scripts\migrate_to_d_drive.ps1`

**.py** (8 файлов):

- `src\golos\__init__.py`
- `src\golos\api\__init__.py`
- `src\golos\audio\__init__.py`
- `src\golos\service\__init__.py`
- `src\golos\transcription\__init__.py`
- `src\main.py`
- `tests\conftest.py`
- `tests\unit\test_example.py`

### Уникальные для 24 na 7

**.api** (1 файлов):

- `Dockerfile.api`

**.bat** (3 файлов):

- `scripts\install_windows_service.bat`
- `scripts\run_api.bat`
- `scripts\run_listener.bat`

**.css** (1 файлов):

- `htmlcov\style_cb_dca529e9.css`

**.db** (1 файлов):

- `src\storage\reflexio.db`

**.html** (66 файлов):

- `htmlcov\class_index.html`
- `htmlcov\function_index.html`
- `htmlcov\index.html`
- `htmlcov\z_04e2950766bc0f15___init___py.html`
- `htmlcov\z_04e2950766bc0f15_main_py.html`
- `htmlcov\z_145eef247bfb46b6___init___py.html`
- `htmlcov\z_33d66654f976a8a9___init___py.html`
- `htmlcov\z_33d66654f976a8a9_adaptive_scoring_py.html`
- `htmlcov\z_33d66654f976a8a9_collector_py.html`
- `htmlcov\z_33d66654f976a8a9_contextor_py.html`
- *...и ещё 56 файлов*

**.js** (2 файлов):

- `htmlcov\coverage_html_cb_497bf287.js`
- `webapp\pwa\service-worker.js`

**.json** (28 файлов):

- `.auto-claude-security.json`
- `.claude_settings.json`
- `.cursor\audit\api_keys_check.json`
- `.cursor\audit\audit_report.json`
- `.cursor\audit\autonomous_cycle_verification.json`
- `.cursor\audit\methodology_compliance_report.json`
- `.cursor\audit\prod_verification_report.json`
- `.cursor\audit\proxy_diagnostics.json`
- `.cursor\config\brightdata_zones.json`
- `.cursor\hooks.json`
- *...и ещё 18 файлов*

**.jsx** (2 файлов):

- `webapp\pwa\components\OneTapCapture.jsx`
- `webapp\pwa\components\SmartReplay.jsx`

**.log** (1 файлов):

- `.cursor\logs\scheduler.log`

**.md** (109 файлов):

- `.cursor\agents\README.md`
- `.cursor\audit\CEB-E_STANDARD.md`
- `.cursor\audit\README.md`
- `.cursor\audit\audit_report.md`
- `.cursor\audit\audit_report_template.md`
- `.cursor\audit\proxy_diagnostics.md`
- `.cursor\governance\README.md`
- `.cursor\memory\README.md`
- `.cursor\memory\decisions.md`
- `.cursor\memory\projectbrief.md`
- *...и ещё 99 файлов*

**.png** (2 файлов):

- `htmlcov\favicon_32_cb_58284776.png`
- `htmlcov\keybd_closed_cb_ce680311.png`

**.ps1** (6 файлов):

- `scripts\final_verification.ps1`
- `scripts\first_launch.ps1`
- `scripts\setup_local_reflexio.ps1`
- `scripts\start_api.ps1`
- `scripts\start_docker_and_up.ps1`
- `scripts\stop_api.ps1`

**.py** (144 файлов):

- `.cursor\agents\audit_agent.py`
- `.cursor\agents\digest_agent.py`
- `.cursor\agents\metrics_agent.py`
- `.cursor\agents\validation_agent.py`
- `.cursor\audit\generate_report.py`
- `.cursor\audit\run_audit.py`
- `.cursor\hooks\auto_governance.py`
- `.cursor\hooks\on_event.py`
- `.cursor\metrics\governance_loop.py`
- `.cursor\validation\__init__.py`
- *...и ещё 134 файлов*

**.service** (1 файлов):

- `reflexio-listener.service`

**.sh** (8 файлов):

- `scripts\backup_supabase.sh`
- `scripts\final_verification.sh`
- `scripts\first_launch.sh`
- `scripts\prod_activation.sh`
- `scripts\run_api.sh`
- `scripts\run_listener.sh`
- `scripts\start_api.sh`
- `scripts\stop_api.sh`

**.skeleton** (1 файлов):

- `scripts\auto_optimize.py.skeleton`

**.sql** (8 файлов):

- `schema.sql`
- `src\storage\migrations\0001_init.sql`
- `src\storage\migrations\0002_indexes.sql`
- `src\storage\migrations\0003_rls_policies.sql`
- `src\storage\migrations\0004_user_preferences.sql`
- `src\storage\migrations\0005_rls_activation.sql`
- `src\storage\migrations\0006_billing.sql`
- `src\storage\migrations\0007_referrals.sql`

**.toml** (1 файлов):

- `pyproject.toml`

**.txt** (1 файлов):

- `.cursor\audit\requirements.txt`

**.wav** (2 файлов):

- `src\storage\uploads\20260131_203932_2ef06b90-6aab-4f2d-88ee-454b8dcb7c3a.wav`
- `src\storage\uploads\20260131_212107_0ad77582-1d42-4b38-b211-13b960f61436.wav`

**.worker** (1 файлов):

- `Dockerfile.worker`

**.yaml** (28 файлов):

- `.cursor\governance\profile.yaml`
- `.cursor\playbooks\audit.yaml`
- `.cursor\playbooks\build-reflexio.yaml`
- `.cursor\playbooks\daily-energy-watch.yaml`
- `.cursor\playbooks\db-migrate.yaml`
- `.cursor\playbooks\digest-reflexio.yaml`
- `.cursor\playbooks\enhancement-plan.yaml`
- `.cursor\playbooks\init.yaml`
- `.cursor\playbooks\level5-upgrade.yaml`
- `.cursor\playbooks\mcp-intelligence.yaml`
- *...и ещё 18 файлов*

**.yml** (9 файлов):

- `.github\workflows\cd.yml`
- `.github\workflows\checklist_audit.yml`
- `.github\workflows\ci.yml`
- `.github\workflows\deploy.yml`
- `.github\workflows\security.yml`
- `docker-compose.vault.yml`
- `docker-compose.yml`
- `observability\alert_rules.yml`
- `observability\prometheus.yml`

**no extension** (8 файлов):

- `.dockerignore`
- `.env`
- `Makefile`
- `digests\.gitkeep`
- `htmlcov\.gitignore`
- `logs\.gitkeep`
- `src\storage\recordings\.gitkeep`
- `src\storage\uploads\.gitkeep`

---

## Стратегия слияния

### Рекомендуемое направление слияния

**База (целевой проект):** `24 na 7`
**Источник (откуда переносим):** `golos`

*Обоснование:* Проект `24 na 7` выбран как база для слияния на основе анализа времени модификации файлов, полноты реализации и версий зависимостей.

### Пошаговый план слияния

#### Шаг 1: Резервное копирование

**Важно:** Создайте резервные копии обоих проектов перед началом слияния.

```bash
# Создайте резервную копию базового проекта
cp -r "D:\24 na 7" "D:\24 na 7.backup"

# Создайте резервную копию исходного проекта
cp -r "C:\Users\serge\Desktop\golos" "C:\Users\serge\Desktop\golos.backup"
```

#### Шаг 2: Проверка системы контроля версий

Убедитесь, что базовый проект находится под контролем версий Git:

```bash
cd "D:\24 na 7"
git status
# Если репозиторий не инициализирован:
# git init
# git add .
# git commit -m "Initial commit before merge"
```

#### Шаг 3: Разрешение конфликтов зависимостей

Перед переносом файлов необходимо разрешить конфликты версий зависимостей:

**Python зависимости:**

| Пакет | Версия в базе | Версия в источнике | Рекомендация |
|-------|---------------|-------------------|--------------|
| fastapi | >=0.110.0 | ==0.104.1 | Проверить совместимость, выбрать новейшую стабильную версию |
| numpy | >=1.26.0 | ==1.26.2 | Проверить совместимость, выбрать новейшую стабильную версию |
| pydantic | >=2.0.0 | ==2.5.0 | Проверить совместимость, выбрать новейшую стабильную версию |
| pydantic-settings | >=2.0.0 | ==2.1.0 | Проверить совместимость, выбрать новейшую стабильную версию |
| python-dotenv | >=1.0.0 | ==1.0.0 | Проверить совместимость, выбрать новейшую стабильную версию |
| sounddevice | >=0.4.6 | ==0.4.6 | Проверить совместимость, выбрать новейшую стабильную версию |
| uvicorn[standard] | >=0.29.0 | ==0.24.0 | Проверить совместимость, выбрать новейшую стабильную версию |
| webrtcvad | >=2.0.10 | ==2.0.10 | Проверить совместимость, выбрать новейшую стабильную версию |

**Действия:**
1. Проанализируйте breaking changes между версиями
2. Обновите requirements.txt или package.json в базовом проекте
3. Установите обновленные зависимости и запустите тесты

#### Шаг 4: Перенос уникальных файлов из golos

В проекте `golos` найдено 25 уникальных файлов, которых нет в `24 na 7`. Эти файлы необходимо перенести:

**Рекомендуемый подход:**

1. **Автоматический перенос** (для файлов с низким риском):
```bash
# Перенести все уникальные файлы, сохраняя структуру директорий
rsync -av --relative \
  --files-from=<(список_уникальных_файлов) \
  "C:\Users\serge\Desktop\golos/" "D:\24 na 7/"
```

2. **Ручной анализ** (рекомендуется для конфигурационных файлов):
   - `.env` файлы - объедините настройки вручную
   - Конфигурации баз данных
   - Файлы с секретами и ключами

#### Шаг 5: Обработка пересекающихся файлов

Обнаружено 5 пересекающихся файлов. Необходимо определить стратегию для каждого:

**Категории файлов:**

1. **Идентичные файлы** - никаких действий не требуется
2. **Файлы с различиями** - требуется анализ:
   - Используйте `git diff` или инструменты сравнения
   - Для кода: объедините улучшения из обоих проектов
   - Для конфигов: выберите наиболее полную версию

**Команда для анализа:**
```bash
# Сравнить конкретный файл
diff -u "D:\24 na 7/путь/к/файлу" "C:\Users\serge\Desktop\golos/путь/к/файлу"

# Или использовать графический инструмент
meld "D:\24 na 7" "C:\Users\serge\Desktop\golos"
```

#### Шаг 6: Объединение зависимостей

Добавьте уникальные зависимости из `golos` в базовый проект:

**Python зависимости для добавления:**
```
black==23.11.0
httpx==0.25.2
isort==5.12.0
loguru==0.7.2
mypy==1.7.0
pyaudio==0.2.14
pytest==7.4.3
pytest-asyncio==0.21.1
pytest-cov==4.1.0
pytest-mock==3.12.0
# ...и ещё 2 пакетов
```

#### Шаг 7: Тестирование объединенного проекта

После завершения слияния проведите всестороннее тестирование:

```bash
# Установите/обновите зависимости
pip install -r requirements.txt

# Запустите тесты
pytest  # для Python
npm test  # для Node.js

# Запустите приложение
# Проверьте основные функции вручную
```

#### Шаг 8: Фиксация результата слияния

После успешного тестирования зафиксируйте результаты:

```bash
git add .
git commit -m "Merge golos into 24 na 7"
```

### Оценка рисков

#### Выявленные риски:

- **Конфликты зависимостей** - обнаружено 8 конфликтующих версий пакетов

#### Меры по снижению рисков:

1. Тщательно тестируйте после обновления зависимостей, проверьте breaking changes

### Рекомендации по приоритетам

**Высокий приоритет:**
1. Резервное копирование обоих проектов
2. Разрешение конфликтов зависимостей
3. Перенос критичных конфигурационных файлов

**Средний приоритет:**
4. Перенос уникальных файлов кода
5. Анализ и слияние пересекающихся файлов

**Низкий приоритет:**
6. Обновление документации
7. Очистка устаревших файлов
8. Оптимизация структуры директорий
