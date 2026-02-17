# Reflexio Android: итоги, проверка компонентов, описание приложения

Документ объединяет: итоги сессии, проверку всех компонентов и полное описание возможностей приложения, потока данных и хранения.

---

## 1. Итоги сессии (февраль 2026)

| Что сделано | Детали |
|-------------|--------|
| Сборка | Исправлен VAD: `Mode.QUALITY` → `Mode.NORMAL` (debug) / `Mode.VERY_AGGRESSIVE` (release). Сборка успешна. |
| UI | Добавлены кнопки «Остановить запись» / «Запустить запись», статус «Запись идёт в фоне…» / «Запись остановлена». |
| Логи | Логи с устройства сохраняются в `android/logs/` (полный и отфильтрованный по Reflexio). Команды — в `android/LOG_README.md`. |
| Документация | `docs/ANDROID_APP_FLOW.md` (алгоритм, граничные случаи), `docs/ANDROID_SESSION_SUMMARY.md` (краткий итог), этот обзор. |

---

## 2. Проверка компонентов

### 2.1 Android-приложение

| Компонент | Путь | Назначение | Статус |
|-----------|------|------------|--------|
| MainActivity | `app/.../ui/MainActivity.kt` | Точка входа, разрешения, запуск/остановка сервиса, UI (кнопки, Diary). | ✅ |
| RecordingApp (Composable) | там же | Состояние разрешений, список записей из БД, кнопки записи. | ✅ |
| RecordingListScreen | `app/.../ui/screens/RecordingListScreen.kt` | Список записей: дата, длительность, статус (Sending… / Done / Failed), опционально транскрипция. | ✅ |
| AudioRecordingService | `app/.../domain/services/AudioRecordingService.kt` | Foreground-сервис: микрофон 16 kHz, VAD, запись WAV, Room, отправка по WebSocket. | ✅ |
| VadSegmentWriter | `app/.../domain/vad/VadSegmentWriter.kt` | WebRTC VAD, буфер кадров 320 сэмплов, сегменты ≥0.5 с после 300 ms тишины. | ✅ |
| IngestWebSocketClient | `app/.../domain/network/IngestWebSocketClient.kt` | Подключение к `baseUrl/ws/ingest`, отправка бинарного WAV, приём `received` → `transcription` или `error`. | ✅ |
| RecordingDatabase | `app/.../data/db/RecordingDatabase.kt` | Room, одна БД `reflexio_recordings.db`, одна сущность Recording. | ✅ |
| RecordingDao | `app/.../data/db/RecordingDao.kt` | insert, getAllRecordings (Flow), update, getById, getRecordingsByStatus. | ✅ |
| Recording (модель) | `app/.../data/model/Recording.kt` | id, filePath, durationSeconds, createdAt, transcription, status (pending_upload/processed/failed). | ✅ |
| AndroidManifest | `app/src/main/AndroidManifest.xml` | RECORD_AUDIO, INTERNET, FOREGROUND_SERVICE, FOREGROUND_SERVICE_MICROPHONE, POST_NOTIFICATIONS; MainActivity, AudioRecordingService (foregroundServiceType=microphone); usesCleartextTraffic. | ✅ |
| BuildConfig | `app/build.gradle.kts` | Debug: SERVER_WS_URL (эмулятор 10.0.2.2:8000), SERVER_WS_URL_DEVICE (реальное устройство, напр. 192.168.1.100:8000). Release: wss://api.reflexio.example.com. | ✅ |

### 2.2 Бэкенд (24 na 7)

| Компонент | Путь | Назначение | Статус |
|-----------|------|------------|--------|
| WebSocket /ws/ingest | `src/api/main.py` | Приём бинарного WAV, ответы `received` → транскрипция → `transcription` или `error`. | ✅ |
| Остальное API | там же | /ingest/audio, /ingest/status, и др. — для других клиентов. | ✅ |

### 2.3 Конфигурация и документация

| Элемент | Расположение | Статус |
|---------|--------------|--------|
| Адрес сервера для устройства | `android/app/build.gradle.kts` → SERVER_WS_URL_DEVICE | ✅ (по умолчанию 192.168.1.100:8000, при необходимости меняется на IP ПК) |
| Логи в проекте | `android/logs/`, команды в `android/LOG_README.md` | ✅ |
| Алгоритм и граничные случаи | `docs/ANDROID_APP_FLOW.md` | ✅ |

---

## 3. Что умеет приложение

- **Запись речи в фоне** — постоянно слушает микрофон (16 kHz, моно, 16 bit).
- **Выделение речи (VAD)** — записывает только сегменты с речью; после 300 ms тишины завершает сегмент; сегменты короче 0.5 с отбрасываются.
- **Сохранение сегментов** — каждый сегмент пишется в WAV-файл и запись о нём — в локальную БД.
- **Отправка на сервер** — по WebSocket на бэкенд 24 na 7; при успехе приходит транскрипция, она сохраняется в БД и отображается в списке.
- **Управление записью** — кнопки «Остановить запись» / «Запустить запись» (вкл/выкл фоновый сервис).
- **Дневник записей** — список всех записей с датой, длительностью и статусом (Sending… / Done / Failed), при наличии — текст транскрипции.

---

## 4. Как работает приложение

1. **Старт** — MainActivity поднимает Room-БД. При ошибке — экран «Database error».
2. **Разрешения** — при отсутствии RECORD_AUDIO (и на API 33+ POST_NOTIFICATIONS) показывается кнопка «Разрешить». После выдачи разрешений запускается сервис записи.
3. **Сервис** — AudioRecordingService в foreground: создаётся канал уведомлений, проверяется RECORD_AUDIO, инициализируется AudioRecord (проверка getMinBufferSize и state). При ошибке (нет микрофона/занят) — сервис останавливается.
4. **Цикл записи** — чтение кадров по 320 сэмплов, передача в VadSegmentWriter. При появлении сегмента речи ≥0.5 с:
   - запись WAV в `filesDir/audio_records/` (имена вида `segment_YYYYMMDD_HHmmss_NNN.wav`);
   - вставка записи в Room (filePath, durationSeconds, createdAt, status=PENDING_UPLOAD);
   - асинхронная отправка файла на бэкенд по WebSocket.
5. **WebSocket** — подключение к `baseUrl/ws/ingest`, отправка бинарного WAV. В ответ: `received`, затем `transcription` (текст) или `error`. По результату в Room: PROCESSED + transcription или FAILED.
6. **UI** — подписка на Flow `getAllRecordings()`, отображение списка. Кнопка «Остановить запись» вызывает stopService; «Запустить запись» — startForegroundService.

Подробная диаграмма и граничные случаи — в `docs/ANDROID_APP_FLOW.md`.

---

## 5. Где хранится информация

| Данные | Где хранятся | Примечание |
|--------|--------------|------------|
| Метаданные записей | **Room** — БД `reflexio_recordings.db` в приватном хранилище приложения (data/data/...). Таблица `recordings`: id, filePath, durationSeconds, createdAt, transcription, status. | При удалении приложения БД удаляется. |
| Аудиофайлы (WAV) | **Файловая система приложения** — каталог `filesDir/audio_records/` (внутреннее хранилище приложения). Имена: `segment_YYYYMMDD_HHmmss_001.wav` и т.д. | Только приложение имеет доступ. При удалении приложения файлы удаляются. |
| Адрес сервера | **BuildConfig** — задаётся при сборке в `app/build.gradle.kts` (SERVER_WS_URL для эмулятора, SERVER_WS_URL_DEVICE для устройства). | Для смены IP/порта нужна пересборка или отдельная настройка (если добавить). |
| Транскрипции с сервера | В той же таблице Room, поле `transcription`, после успешного ответа WebSocket. | Отображаются в Diary под записью. |

Никакие секреты и сырые аудио не логируются; аудио не попадает в публичные каталоги без явной настройки (соответствует правилам безопасности проекта).

---

## 6. Зависимости потока данных

- **Эмулятор:** сервер на ПК доступен как `10.0.2.2:8000` (BuildConfig.SERVER_WS_URL).
- **Реальное устройство:** телефон и ПК с бэкендом должны быть в одной сети; в BuildConfig.SERVER_WS_URL_DEVICE указать IP ПК (например 192.168.1.x). Иначе WebSocket даёт таймаут, статус записей — Failed.
- На эмуляторе виртуальный микрофон часто даёт I/O ошибки и почти не даёт речи → тестирование записи и VAD лучше на реальном телефоне.

---

## 7. Краткая сводка

- **Приложение:** фоновый диктофон с VAD, локальное хранение WAV и метаданных в Room, отправка сегментов на бэкенд по WebSocket, отображение списка и транскрипций в Diary.
- **Компоненты:** UI, сервис, VAD, БД, WebSocket-клиент и бэкенд `/ws/ingest` проверены и соответствуют описанному потоку.
- **Хранение:** аудио — в `filesDir/audio_records/`, метаданные и транскрипции — в Room `reflexio_recordings.db`; всё в приватном хранилище приложения.
