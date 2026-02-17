# REFLEXIO — Полный отчёт и настройка

**Дата:** февраль 2026  
**Статус:** MVP готов, Phase 2 внедрена  
**Версия:** 1.0

---

## Краткий итог

Reflexio — персональная когнитивная система для осмысления дня — **работает end-to-end**.

- **Android приложение** записывает речь в фоне
- **WebSocket отправляет** WAV на бэкенд
- **Бэкенд** транскрибирует (Whisper), при необходимости анализирует через **LLM** (Gemini, Claude, OpenAI)
- **Итог дня** (GET /digest/daily) подводится по записям за день
- **Дневник** показывает записи со статусом и транскрипцией
- **Аналитика** — экран с пунктом «Итог дня» (работает) и заглушками «Скоро» (отчёт за месяц, характеристика, работа/сеть, свой LLM)

**Что нужно:** запустить бэкенд на ПК, указать IP в приложении, при желании подключить свой LLM API (Gemini/Claude/OpenAI).

---

## Что сделано (соответствует коду)

### Android приложение

- **Запись в фоне:** Foreground Service, VAD (только речь), сегменты ≥0.5 с, WAV 16 kHz моно.
- **Дневник (Diary):** Room, список записей — дата, длительность, статус (Sending… / Done / Failed), транскрипция.
- **WebSocket:** отправка бинарного WAV на `ws://[SERVER]/ws/ingest`; в ответ приходит **только** `{ type: "transcription", text, language }` (без emotion/actions в ответе WS — анализ делается на бэкенде отдельно).
- **Кнопки:** «Запустить/Остановить запись», «Итог дня», «Аналитика».
- **Экран «Итог дня»:** GET `http://[SERVER]:8000/digest/daily?date=YYYY-MM-DD` → summary_text, key_themes, emotions, actions, total_recordings, total_duration, repetitions.
- **Экран «Аналитика»:** пункт «Итог дня» (открывает тот же экран), остальное — «Скоро» (отчёт за месяц, характеристика, работа и сеть, подключить свой LLM).

**Структура (фактическая):**  
`MainActivity.kt` → `RecordingApp`, `WelcomeBlock`; экраны: `DailySummaryScreen`, `AnalyticsScreen`, `RecordingListScreen`. Сервис: `AudioRecordingService`, VAD: `VadSegmentWriter`, сеть: `IngestWebSocketClient`. БД: Room (`RecordingDatabase`, `RecordingDao`).

### Бэкенд (Python)

- **Один модуль API:** [src/api/main.py](src/api/main.py) — все эндпоинты здесь (нет отдельных `websocket.py`, `analyze.py`, `digest.py`).
- **WebSocket** `/ws/ingest`: приём WAV → сохранение в `uploads/` → транскрипция (Whisper) → сохранение в SQLite (`ingest_queue` + `transcriptions`) → ответ клиенту `{ type: "transcription", text, language }`.
- **POST** `/analyze/text`: тело `{ transcription, transcription_id?, user_context? }` → LLM (summary, emotions, actions, topics, urgency) → при указании `transcription_id` сохранение в `recording_analyses`.
- **GET** `/digest/daily?date=`: агрегация транскрипций и (при наличии) `recording_analyses` за день → `summary_text`, `key_themes`, `emotions`, `actions`, `total_recordings`, `total_duration`, `repetitions`.
- **LLM:** один файл [src/llm/providers.py](src/llm/providers.py) — OpenAI, Anthropic, **Google Gemini**. Выбор через переменную окружения `LLM_PROVIDER` (openai | anthropic | **google**).

**Важно:** эндпоинта **GET /analytics/stats** в проекте нет. Экран «Аналитика» в приложении показывает только «Итог дня» и заглушки «Скоро»; отдельный API для статистики по дням/темам/паттернам не реализован.

---

## Переменные окружения (фактические)

Бэкенд читает настройки из [src/utils/config.py](src/utils/config.py) и из файла **.env** в корне проекта (pydantic_settings).

```
# LLM (один провайдер)
LLM_PROVIDER=google
GEMINI_API_KEY=...          # или GOOGLE_API_KEY для Gemini

# Альтернативы:
# LLM_PROVIDER=anthropic
# ANTHROPIC_API_KEY=...      # не CLAUDE_API_KEY

# LLM_PROVIDER=openai
# OPENAI_API_KEY=...

# Модель (опционально)
LLM_MODEL_ACTOR=gemini-1.5-flash

# Сервер
# HOST/PORT задаются при запуске: uvicorn ... --host 0.0.0.0 --port 8000
```

База данных — SQLite `src/storage/reflexio.db` (путь из `settings.STORAGE_PATH`). Отдельная переменная `DATABASE_URL` в конфиге не используется для основного потока.

---

## Как запустить

### 1. Бэкенд на ПК

```powershell
cd "d:\24 na 7"
uvicorn src.api.main:app --host 0.0.0.0 --port 8000
```

Или с модулем: `python -m uvicorn src.api.main:app --host 0.0.0.0 --port 8000`

### 2. IP ПК

```powershell
ipconfig | findstr /i "IPv4"
```

### 3. IP в приложении

**Файл:** [android/app/build.gradle.kts](android/app/build.gradle.kts), секция `buildTypes { debug { ... } }`:

```kotlin
buildConfigField("String", "SERVER_WS_URL_DEVICE", "\"ws://192.168.0.105:8000\"")
```

Подставить свой IP вместо `192.168.0.105`. Не `val SERVER_WS_URL_DEVICE` — это строка внутри `buildConfigField`.

### 4. Сборка и установка на телефон

```powershell
cd "d:\24 na 7\android"
.\gradlew installDebug
```

Или только на выбранное устройство: `$env:ANDROID_SERIAL = "серийник"; .\gradlew installDebug`

---

## Ошибка «Итог дня»

- Бэкенд не запущен → запустить uvicorn с `--host 0.0.0.0`.
- Неверный IP в приложении → в `build.gradle.kts` в `SERVER_WS_URL_DEVICE` указать IP ПК, пересобрать и переустановить приложение.
- Разные сети → телефон и ПК в одной Wi‑Fi.
- В браузере с ПК проверить: `http://[твой_IP]:8000/docs` и вызов `GET /digest/daily?date=сегодня`.

---

## Подключение своего Gemini

1. Ключ: [Google AI Studio](https://aistudio.google.com/) → Get API key.
2. На ПК, где запускается бэкенд:
   - В `.env` в корне проекта: `LLM_PROVIDER=google`, `GEMINI_API_KEY=твой_ключ`, при необходимости `LLM_MODEL_ACTOR=gemini-1.5-flash`.
   - Или в PowerShell перед запуском: `$env:LLM_PROVIDER="google"; $env:GEMINI_API_KEY="..."; uvicorn ...`
3. Перезапустить бэкенд. Анализ (POST /analyze/text) и итог дня (GET /digest/daily) пойдут через Gemini.

Для Claude используется **ANTHROPIC_API_KEY** (не CLAUDE_API_KEY).

---

## Установка на телефон по USB

Режим разработчика → отладка по USB → подключить кабель → в Android Studio выбрать устройство и Run, либо `adb devices`, затем `$env:ANDROID_SERIAL="..."; .\gradlew installDebug`.

---

## Что в документе было неверно (исправлено здесь)

| В оригинале | Как на самом деле |
|-------------|-------------------|
| Отдельные файлы `websocket.py`, `analyze.py`, `digest.py` | Всё в [src/api/main.py](src/api/main.py) |
| Отдельные `gemini.py`, `claude.py`, `openai.py` | Один файл [src/llm/providers.py](src/llm/providers.py) |
| GET /analytics/stats (статистика, темы, паттерны) | Такого эндпоинта нет; в приложении только заглушки «Скоро» |
| WebSocket возвращает emotion, actions, topics, urgency | WebSocket возвращает только transcription (text, language); анализ — через POST /analyze/text и дайджест |
| `val SERVER_WS_URL_DEVICE` в коде | В build.gradle.kts: `buildConfigField("String", "SERVER_WS_URL_DEVICE", "\"ws://...\"")`; в коде приложения — `BuildConfig.SERVER_WS_URL_DEVICE` |
| CLAUDE_API_KEY для Claude | В проекте используется **ANTHROPIC_API_KEY** |
| DATABASE_URL=sqlite:///reflexio.db | БД — `settings.STORAGE_PATH / "reflexio.db"` (по умолчанию `src/storage/reflexio.db`) |

---

Остальное в твоём отчёте (чеклисты, шаги запуска, диагностика «Итог дня», получение ключа Gemini, .env, установка по USB) по смыслу верно; выше — уточнения под актуальную кодовую базу.
