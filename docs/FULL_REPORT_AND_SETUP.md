# Полный отчёт и настройка: Reflexio Android + бэкенд

## 1. Полный отчёт по проекту

### Что сделано

**Android-приложение (Reflexio Recording):**
- Запись речи в фоне (Foreground Service), VAD (только речь), сегменты ≥0.5 с.
- Дневник записей (Room): дата, длительность, статус (Sending… / Done / Failed), транскрипция.
- Отправка WAV на бэкенд по WebSocket `/ws/ingest`.
- Приветствие по времени суток и короткое описание с хуками на главном экране.
- Кнопки: «Остановить/Запустить запись», «Итог дня», «Аналитика».
- Экран «Итог дня»: загрузка `GET /digest/daily?date=сегодня`, отображение summary, темы, эмоции, действия, статистика.
- Экран «Аналитика»: Итог дня (работает), заглушки «Скоро» — отчёт за месяц, характеристика, работа и сеть, блок «Подключить свой LLM».

**Бэкенд (24 na 7):**
- WebSocket `/ws/ingest`: приём WAV, транскрипция (Whisper), сохранение в БД (ingest_queue + transcriptions).
- POST `/analyze/text`: анализ текста (summary, emotions, actions, topics, urgency), сохранение в recording_analyses при указании transcription_id.
- GET `/digest/daily?date=`: дневной итог в формате для приложения (summary_text, key_themes, emotions, actions, total_recordings, total_duration, repetitions).
- Поддержка LLM: OpenAI, Anthropic, **Google Gemini** (через переменные окружения).

**Документация:**
- ANDROID_OVERVIEW.md, ANDROID_APP_FLOW.md, ANDROID_SESSION_SUMMARY.md, DAILY_DIGEST_EXAMPLE.md, LOG_README.md, план в docs/plan/files.

---

## 2. Ошибка «Итог дня»

При нажатии «Итог дня» приложение делает запрос на `http://<адрес_сервера>:8000/digest/daily?date=...`. Ошибка обычно из‑за одного из пунктов ниже.

### 2.1 Бэкенд не запущен

На ПК должен быть запущен сервер:

```powershell
cd "d:\24 na 7"
uvicorn src.api.main:app --host 0.0.0.0 --port 8000
```

`--host 0.0.0.0` нужен, чтобы принимать запросы с телефона в локальной сети.

### 2.2 Неверный IP сервера в приложении

В приложении используется адрес из `BuildConfig.SERVER_WS_URL_DEVICE`. По умолчанию в коде: `192.168.1.100`. Это должен быть **IP вашего ПК** в той же Wi‑Fi сети, что и телефон.

Как узнать IP ПК (Windows):

```powershell
ipconfig | findstr /i "IPv4"
```

Например, если получили `192.168.0.105`, в проекте нужно подставить его.

**Где менять:** [android/app/build.gradle.kts](android/app/build.gradle.kts), секция `buildTypes { debug { ... } }`:

```kotlin
buildConfigField("String", "SERVER_WS_URL_DEVICE", "\"ws://192.168.0.105:8000\"")
```

Замените `192.168.0.105` на свой IP. Для «Итог дня» приложение подставляет `http://` вместо `ws://` к этому же хосту и порту.

После изменения: **Build → Rebuild Project**, затем снова установить приложение на телефон (Run с выбранным устройством или `.\gradlew installDebug` с `ANDROID_SERIAL`).

### 2.3 Телефон и ПК в разных сетях

Телефон и компьютер должны быть в одной Wi‑Fi сети (один роутер). Иначе запросы с телефона до ПК не дойдут.

### 2.4 Краткий чеклист

1. Запустить бэкенд на ПК: `uvicorn src.api.main:app --host 0.0.0.0 --port 8000`.
2. Узнать IP ПК: `ipconfig` → IPv4.
3. В `android/app/build.gradle.kts` в `SERVER_WS_URL_DEVICE` указать этот IP (например `ws://192.168.0.105:8000`).
4. Пересобрать и заново установить приложение на телефон.
5. Убедиться, что телефон в той же Wi‑Fi, что и ПК.

---

## 3. Подключение своего Gemini к приложению

Обработка текста (анализ записей, итог дня) выполняется **на бэкенде**. Свою модель Gemini подключаете через настройку бэкенда, а не в самом приложении на телефоне.

### 3.1 API-ключ Gemini

1. Зайти в [Google AI Studio](https://aistudio.google.com/) (или Google Cloud Console для Gemini API).
2. Создать/скопировать API-ключ для Gemini.

### 3.2 Настройка бэкенда под Gemini

Задайте переменные окружения **на ПК, где запускаете бэкенд** (в `.env` в корне проекта или в системе):

```env
LLM_PROVIDER=google
GEMINI_API_KEY=ваш_ключ_от_google_ai_studio
```

Или вместо `GEMINI_API_KEY` можно использовать:

```env
GOOGLE_API_KEY=ваш_ключ
```

Опционально — явно указать модель (по умолчанию в коде используются имена вида `gemini-3-flash`; актуальные имена смотрите в документации Google):

```env
LLM_MODEL_ACTOR=gemini-1.5-flash
LLM_MODEL_CRITIC=gemini-1.5-pro
```

Пример запуска с переменными в PowerShell:

```powershell
$env:LLM_PROVIDER = "google"
$env:GEMINI_API_KEY = "ваш_ключ"
uvicorn src.api.main:app --host 0.0.0.0 --port 8000
```

После этого анализ текста (POST `/analyze/text`, извлечение фактов и эмоций для дайджеста, итог дня) будет идти через ваш Gemini.

### 3.3 Где в коде используется LLM

- [src/llm/providers.py](src/llm/providers.py) — фабрика `get_llm_client()`: читает `LLM_PROVIDER`, при `google` создаёт `GoogleGeminiClient` и берёт ключ из `GEMINI_API_KEY` или `GOOGLE_API_KEY`.
- Анализ записей (summary, emotions, actions, topics) и дайджесты используют этого клиента через [src/summarizer/few_shot.py](src/summarizer/few_shot.py) и [src/digest/generator.py](src/digest/generator.py).

Приложение на телефоне к API ключам не обращается: оно только шлёт аудио на бэкенд и запрашивает «Итог дня» и аналитику. Всё, что связано с Gemini, выполняется на сервере.

---

## 4. Установка приложения на телефон по USB

Чтобы ставить сборку именно на телефон (а не на эмулятор):

**Вариант A — Android Studio:** в выпадающем списке устройств выбрать телефон (например, Pixel 9 Pro), затем Run.

**Вариант B — командная строка (только телефон):**

```powershell
cd "d:\24 na 7\android"
$env:ANDROID_SERIAL = "53031FDAP000ZA"   # замените на свой серийник из adb devices
.\gradlew installDebug
```

Серийник смотрите: `adb devices`.

---

## 5. Полезные файлы

| Назначение | Файл/место |
|------------|------------|
| Обзор приложения, хранение данных | [docs/ANDROID_OVERVIEW.md](ANDROID_OVERVIEW.md) |
| Алгоритм, граничные случаи | [docs/ANDROID_APP_FLOW.md](ANDROID_APP_FLOW.md) |
| Пример вечернего итога | [docs/DAILY_DIGEST_EXAMPLE.md](DAILY_DIGEST_EXAMPLE.md) |
| Логи с телефона | [android/LOG_README.md](android/LOG_README.md), папка `android/logs/` |
| Адрес сервера в приложении | [android/app/build.gradle.kts](android/app/build.gradle.kts) — `SERVER_WS_URL_DEVICE` |
| Подключение Gemini на бэкенде | переменные `LLM_PROVIDER=google`, `GEMINI_API_KEY` или `GOOGLE_API_KEY` |
