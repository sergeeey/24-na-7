# Reflexio Android App

Мобильное приложение для фоновой записи речи 24/7 с последующей отправкой на сервер Reflexio.

## Требования

- Android Studio Hedgehog (2023.1.1) или новее
- JDK 17
- Min SDK 29 (Android 10), Target SDK 34

## Как открыть

1. Запустите Android Studio.
2. **File → Open** и выберите папку `android` (корень этого проекта).
3. Дождитесь синхронизации Gradle (Sync Project with Gradle Files).
4. Подключите устройство или запустите эмулятор (API 29+).
5. **Run → Run 'app'.**

## Разрешения

При первом запуске нужно выдать разрешения:
- **Микрофон** — для записи аудио.
- **Уведомления** (Android 13+) — для отображения постоянного уведомления о записи.

## Структура (после Недели 3)

- `app/src/main/kotlin/com/reflexio/app/`
  - **data/**
    - **db/** — Room: `RecordingDatabase.kt`, `RecordingDao.kt`.
    - **model/** — сущность `Recording.kt` (id, filePath, durationSeconds, createdAt, transcription, status).
  - **domain/**
    - **vad/** — `VadSegmentWriter.kt`: WebRTC VAD (16 kHz, кадр 320 сэмплов), буфер сегмента; при 300 ms тишины после речи отдаёт сегмент; сегменты короче 0.5 с отбрасываются.
    - **services/** — `AudioRecordingService.kt`: фоновый сервис; читает по 320 сэмплов, передаёт в VAD; каждый завершённый сегмент пишется в WAV и вставляется в Room.
  - **ui/**
    - `MainActivity.kt` — главный экран: заголовок и список записей из БД.
    - **screens/** — `RecordingListScreen.kt`: список записей (дата/время, длительность, статус).

Аудио сохраняется в `filesDir/audio_records/` как сегменты речи (`segment_yyyyMMdd_HHmmss_NNN.wav`). Записываются только фрагменты с речью (VAD отсекает тишину и шум). Каждый сегмент — одна запись в Room. На Неделе 4 статусы будут обновляться при отправке на сервер (WebSocket).

### Статусы записей

- `pending_upload` — сохранено локально, ещё не отправлено.
- `uploaded` — отправлено на сервер.
- `processed` — обработано на сервере (например, есть транскрипция).
- `failed` — ошибка при отправке или обработке.

## Roadmap

См. [docs/ANDROID_APP_ROADMAP.md](../docs/ANDROID_APP_ROADMAP.md): Room + локальный кеш (Неделя 2 — сделано), VAD (Неделя 3 — сделано), далее WebSocket, UI дневника.
