# Reflexio Android App — Roadmap

**Цель:** мобильное приложение с фоновой записью 24/7, VAD, отправкой на сервер и просмотром дневника.

---

## Стек

| Компонент   | Технология              |
|------------|--------------------------|
| Язык       | Kotlin                   |
| UI         | Jetpack Compose          |
| Аудио      | AudioRecord + MediaRecorder |
| VAD        | WebRTC VAD (offline)     |
| Сеть       | OkHttp + WebSocket       |
| Фон        | WorkManager / Foreground Service |
| БД         | Room                     |

---

## Недели 1–4

- **Неделя 1:** Setup, AudioRecordingService, тесты записи.
- **Неделя 2:** WebRTC VAD, Room, локальный кеш.
- **Неделя 3:** WebSocket-клиент, отправка аудио, получение транскрипции (реализовано: `IngestWebSocketClient`, `/ws/ingest` на backend).
- **Неделя 4:** Compose UI, уведомления, настройки, тесты и релиз.

---

## Ресурсы

- [Jetpack Compose](https://developer.android.com/jetpack/compose)
- [AudioRecord](https://developer.android.com/reference/android/media/AudioRecord)
- [WebRTC VAD](https://github.com/wiseman/py-webrtcvad) (на Android — JNI или порт)
- [Room](https://developer.android.com/training/data-storage/room)
- [OkHttp WebSocket](https://square.github.io/okhttp/)

---

## Первый шаг

1. Открыть папку [android/](../android/) в Android Studio (Open an existing project).
2. Синхронизировать Gradle (Sync Project with Gradle Files).
3. Запустить на эмуляторе или устройстве (API 29+).

Исходный код:
- **Сервис записи:** [android/app/src/main/kotlin/com/reflexio/app/domain/services/AudioRecordingService.kt](../android/app/src/main/kotlin/com/reflexio/app/domain/services/AudioRecordingService.kt)
- **UI:** [android/app/src/main/kotlin/com/reflexio/app/ui/MainActivity.kt](../android/app/src/main/kotlin/com/reflexio/app/ui/MainActivity.kt)
- Подробности: [android/README.md](../android/README.md).
