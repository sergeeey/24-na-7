# Неделя 3: Voice Activity Detection (VAD)

## Зачем VAD перед WebSocket

- **Батарея:** приложение 24/7 — запись только при речи снижает нагрузку и объём данных.
- **Трафик:** на сервер уходят только сегменты с речью, без тишины и шума.
- **Качество:** сервер получает уже отфильтрованные фрагменты.
- **Room:** сегменты сохраняются как отдельные `Recording` (схема уже есть).

Порядок: сначала VAD (сегменты в Room), затем Неделя 4 — WebSocket (отправка сегментов).

---

## Целевая структура после изменений

```
android/app/src/main/kotlin/com/reflexio/app/
├── data/
│   ├── db/           (без изменений)
│   └── model/        (без изменений)
├── domain/
│   ├── services/
│   │   └── AudioRecordingService.kt   (MODIFY: цикл с VAD, сегменты в файлы + Room)
│   └── vad/
│       └── VadSegmentWriter.kt        (NEW: VAD + буфер сегмента, запись WAV)
└── ui/                (без изменений)
```

Дополнительно:
- **android/settings.gradle.kts** — репозиторий JitPack (если ещё нет).
- **android/app/build.gradle.kts** — зависимость WebRTC VAD.

---

## Шаг 1. Зависимость WebRTC VAD и JitPack

### 1.1 Репозиторий JitPack

В [android/settings.gradle.kts](android/settings.gradle.kts) в блок `repositories` добавить:

```kotlin
dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {
        google()
        mavenCentral()
        maven { url = uri("https://jitpack.io") }
    }
}
```

### 1.2 Зависимость в app

В [android/app/build.gradle.kts](android/app/build.gradle.kts) в `dependencies` добавить:

```kotlin
implementation("com.github.gkonovalov.android-vad:webrtc:2.0.10")
```

Библиотека: WebRTC VAD (GMM), 16 kHz, frame 320 samples (20 ms). Подходит под текущий формат записи (16 kHz, mono, 16-bit).

---

## Шаг 2. Константы VAD (в сервисе или общие)

Параметры из документации WebRTC VAD для 16 kHz:

| Параметр            | Значение | Комментарий                          |
|---------------------|----------|--------------------------------------|
| Sample rate         | 16 kHz   | Совпадает с `AudioRecordingService`  |
| Frame size          | 320      | 20 ms                                |
| Mode                | VERY_AGGRESSIVE | Меньше ложных срабатываний   |
| Silence duration    | 300 ms   | Конец сегмента после тишины          |
| Speech duration     | 50 ms    | Минимальная длительность речи        |

Для перевода «тишина N мс» в число кадров: `silenceFrames = 300 / 20 = 15` кадров подряд без речи → завершить сегмент.

Минимальная длина сегмента (опционально): не сохранять сегменты короче 0.5–1.0 с, чтобы отсечь короткие щелчки. В плане используем **минимальная длительность 0.5 с** (можно вынести в константу и потом настроить).

---

## Шаг 3. Класс VadSegmentWriter (domain/vad)

Создать [android/app/src/main/kotlin/com/reflexio/app/domain/vad/VadSegmentWriter.kt](android/app/src/main/kotlin/com/reflexio/app/domain/vad/VadSegmentWriter.kt).

**Назначение:** принимать PCM-кадры (320 samples = 640 bytes), отдавать их в VAD; при переходе «речь → тишина» (после N кадров тишины) отдавать собранный сегмент наружу (запись в файл и в Room делает сервис).

**Поведение:**

1. Инициализация: создать WebRTC VAD (16 kHz, frame 320, VERY_AGGRESSIVE, silenceDurationMs 300, speechDurationMs 50). Хранить размер кадра в сэмплах: `VAD_FRAME_SIZE = 320`.
2. Состояние: `inSpeech`, буфер сэмплов текущего сегмента, счётчик кадров тишины подряд.
3. На каждый кадр (320 shorts → 640 bytes):
   - `vad.isSpeech(byteArray)`.
   - Если речь: `inSpeech = true`, счётчик тишины = 0, добавить кадр в буфер.
   - Если не речь и `inSpeech`: добавить кадр в буфер (хвост), увеличить счётчик тишины. Если счётчик тишины ≥ 15 (300 ms): считать сегмент законченным — вернуть буфер (или список ShortArray), сбросить буфер и `inSpeech`, сбросить счётчик.
   - Если не речь и не `inSpeech`: счётчик тишины = 0, буфер не трогать.
4. Минимальная длина: если при завершении сегмента длительность < 0.5 с (например, `samples.size < 16000 * 0.5`), сегмент не возвращать (выбросить).
5. Ресурсы: метод `close()` для освобождения VAD (библиотека может требовать явного закрытия).

**Интерфейс (пример):**

- Конструктор: `VadSegmentWriter(sampleRateHz: Int = 16000)` — внутри создаётся VAD.
- `fun processFrame(samples: ShortArray): List<ShortArray>?` — принять один кадр 320 samples; вернуть список завершённых сегментов (обычно 0 или 1 элемент). Если сегмент отфильтрован по минимальной длительности — возвращать пустой список.
- `fun flush(): ShortArray?` — при остановке записи отдать последний накопленный сегмент (если есть и он не короче минимума).
- `fun close()` — освободить VAD.

Альтернатива для простоты: вместо возврата списка сегментов — callback `onSegment(samples: ShortArray)` и вызывать его при завершении сегмента.

**Важно:** библиотека `com.github.gkonovalov.android-vad:webrtc` в Kotlin используется так (из README):

```kotlin
import com.github.gkonovalov.android.vad.webrtc.VadWebRTC
import com.github.gkonovalov.android.vad.webrtc.SampleRate
import com.github.gkonovalov.android.vad.webrtc.FrameSize
import com.github.gkonovalov.android.vad.webrtc.Mode

VadWebRTC(
    sampleRate = SampleRate.SAMPLE_RATE_16K,
    frameSize = FrameSize.FRAME_SIZE_320,
    mode = Mode.VERY_AGGRESSIVE,
    silenceDurationMs = 300,
    speechDurationMs = 50
).use { vad ->
    val isSpeech = vad.isSpeech(audioData)  // ByteArray, 640 bytes
}
```

Пакет в исходниках библиотеки: `com.konovalov.vad.webrtc` (класс `VadWebRTC`). В JitPack-артефакте путь может быть `com.github.gkonovalov.android.vad.webrtc` — при сборке проверить импорты.

### Готовый код VadSegmentWriter.kt (каркас)

```kotlin
package com.reflexio.app.domain.vad

import java.io.Closeable

private const val SAMPLE_RATE = 16000
private const val VAD_FRAME_SIZE = 320
private const val SILENCE_FRAMES_TO_END = 15  // 300ms / 20ms
private const val MIN_SEGMENT_SAMPLES = (SAMPLE_RATE * 0.5).toInt()  // 0.5 sec

class VadSegmentWriter : Closeable {

    private val vad = VadWebRTC(  // import from library
        sampleRate = SampleRate.SAMPLE_RATE_16K,
        frameSize = FrameSize.FRAME_SIZE_320,
        mode = Mode.VERY_AGGRESSIVE,
        silenceDurationMs = 300,
        speechDurationMs = 50
    )
    private val segmentBuffer = mutableListOf<Short>()
    private var inSpeech = false
    private var silenceFrameCount = 0

    fun processFrame(samples: ShortArray): List<ShortArray>? {
        require(samples.size == VAD_FRAME_SIZE)
        val bytes = samples.toByteArray()
        val isSpeech = vad.isSpeech(bytes)
        if (isSpeech) {
            inSpeech = true
            silenceFrameCount = 0
            segmentBuffer.addAll(samples.toList())
            return null
        }
        if (inSpeech) {
            segmentBuffer.addAll(samples.toList())
            silenceFrameCount++
            if (silenceFrameCount >= SILENCE_FRAMES_TO_END) {
                val segment = segmentBuffer.toShortArray()
                segmentBuffer.clear()
                inSpeech = false
                silenceFrameCount = 0
                if (segment.size >= MIN_SEGMENT_SAMPLES) return listOf(segment)
            }
            return null
        }
        return null
    }

    fun flush(): ShortArray? {
        val segment = if (segmentBuffer.size >= MIN_SEGMENT_SAMPLES) segmentBuffer.toShortArray() else null
        segmentBuffer.clear()
        return segment
    }

    override fun close() {
        vad.close()
    }

    private fun ShortArray.toByteArray(): ByteArray = ByteArray(size * 2) { i ->
        val s = this[i / 2]
        if (i % 2 == 0) (s.toInt() and 0xFF).toByte() else ((s.toInt() shr 8) and 0xFF).toByte()
    }
}
```

Импорты VAD добавить после подключения зависимости (имена пакетов уточнить по JAR: `VadWebRTC`, `SampleRate`, `FrameSize`, `Mode`). В `flush()` после возврата сегмента очистить `segmentBuffer`.

---

## Шаг 4. Интеграция в AudioRecordingService

В [android/app/src/main/kotlin/com/reflexio/app/domain/services/AudioRecordingService.kt](android/app/src/main/kotlin/com/reflexio/app/domain/services/AudioRecordingService.kt):

### 4.1 Основной цикл записи

- Не создавать один файл на весь сеанс. Вместо этого в цикле:
  - Читать с `AudioRecord` кадры по **320 сэмплов** (размер кадра VAD).
  - Если прочитано меньше 320 — накопить в буфер до 320 или обработать остаток при остановке (см. ниже).
  - Передавать кадр в `VadSegmentWriter.processFrame(samples)`.
  - Если возвращается завершённый сегмент (ShortArray): записать его в WAV в `filesDir/audio_records/`, сформировать имя типа `segment_yyyyMMdd_HHmmss_XXX.wav`, дописать заголовок WAV, вставить `Recording` в Room (как сейчас после записи), при желании вызвать `sendAudioToServer(file)`.

### 4.2 Запись одного сегмента в WAV

Вынести в отдельную функцию (или в `VadSegmentWriter`/отдельный хелпер):

- Вход: `ShortArray` (PCM 16-bit mono), `sampleRate = 16000`, `outputFile: File`.
- Действия: записать 44-байтный заголовок (placeholder), затем PCM (ShortArray → bytes little-endian), затем переписать заголовок с правильным размером данных.
- Использовать существующие `writeWavHeader`, `writeInt`, `writeShort` и конвертацию ShortArray в ByteArray из текущего сервиса.

### 4.3 Жизненный цикл VAD

- При старте записи (в той же корутине, где цикл): создать `VadSegmentWriter`, в цикле вызывать `processFrame`.
- При остановке (`isRecording = false`): выйти из цикла, вызвать `vadSegmentWriter.flush()`, если есть последний сегмент — записать его в WAV и Room, затем `vadSegmentWriter.close()`.

### 4.4 Обработка «неполного кадра»

- Если `record.read()` вернул, например, 200 сэмплов — накапливать в буфер до 320, затем отдавать кадр в VAD. При остановке оставшиеся сэмплы можно передать в VAD нулями до 320 или отдать во `flush()` как финальный неполный кадр (зависит от API VAD — обычно нужны ровно 320).

### 4.5 Удаление старой логики «одного файла»

- Убрать создание одного `recording_$timestamp.wav` в начале и один вызов `recordAudioToFile(audioFile)`. Заменить на цикл «читать 320 → VAD → при завершении сегмента писать WAV + insert Room».

Итог: сервис по-прежнему один (Foreground, уведомление), но пишет много маленьких WAV-файлов (сегментов) и столько же записей в Room со статусом `pending_upload`.

### Псевдокод цикла записи с VAD

```kotlin
val audioDir = File(filesDir, "audio_records").apply { mkdirs() }
val frameBuffer = ShortArray(VAD_FRAME_SIZE)
var frameOffset = 0
VadSegmentWriter().use { vadWriter ->
    while (isRecording) {
        val read = record.read(frameBuffer, frameOffset, VAD_FRAME_SIZE - frameOffset)
        if (read > 0) frameOffset += read
        if (frameOffset >= VAD_FRAME_SIZE) {
            vadWriter.processFrame(frameBuffer)?.forEach { segmentSamples ->
                val file = File(audioDir, "segment_${timestamp()}_${index}.wav")
                writeSegmentToWav(segmentSamples, file)
                insertRecording(file, segmentSamples.size)
            }
            frameOffset = 0
        }
        delay(5)
    }
    vadWriter.flush()?.let { segmentSamples ->
        val file = File(audioDir, "segment_${timestamp()}_final.wav")
        writeSegmentToWav(segmentSamples, file)
        insertRecording(file, segmentSamples.size)
    }
}
```

Функции `writeSegmentToWav(shortArray, File)` и `insertRecording(file, sampleCount)` реализовать по аналогии с текущей записью WAV и вставкой в Room.

---

## Шаг 5. Сохранение сегментов в Room

- Каждый сохранённый WAV-сегмент — одна запись в БД, как сейчас:
  - `filePath`, `durationSeconds` (длина сегмента в сэмплах / 16000), `createdAt` (System.currentTimeMillis() при сохранении), `transcription = null`, `status = PENDING_UPLOAD`.
- Схема Room и DAO не меняются. Список в UI по-прежнему показывает все записи (теперь это сегменты речи).

---

## Шаг 6. Тестирование

- Запуск приложения, включение записи.
- Проговорить несколько фраз с паузами > 0.3 с: должны появляться отдельные сегменты в списке и в `filesDir/audio_records/`.
- Тишина: новых сегментов не должно появляться (или очень мало при шуме).
- Остановка сервиса: последний сегмент должен сохраниться через `flush()`.
- Проверка Database Inspector: таблица `recordings` пополняется сегментами с разными `createdAt` и `filePath`.

---

## Шаг 7. Документация

- Обновить [android/README.md](android/README.md):
  - В структуре указать `domain/vad/VadSegmentWriter.kt` и роль VAD (сегментация по речи).
  - Кратко описать: запись только сегментов с речью, параметры (16 kHz, frame 320, VERY_AGGRESSIVE, silence 300 ms), минимальная длина сегмента 0.5 с.
- При желании обновить [docs/ANDROID_APP_ROADMAP.md](docs/ANDROID_APP_ROADMAP.md): отметить Неделю 3 (VAD) как выполненную после внедрения.

---

## Риски и примечания

- **Пакет VAD:** точное имя пакета (например `com.github.gkonovalov.android.vad.webrtc`) уточнить по зависимостям после добавления библиотеки; при несовпадении — поправить импорты.
- **Производительность:** один кадр 20 ms обрабатывается быстро; цикл на Dispatchers.Default не должен блокировать UI.
- **Миграция данных:** старые записи (цельный файл за сеанс) остаются в Room; новые записи — сегменты. При необходимости можно добавить поле `type` (full_session / segment) позже.

---

## Краткий чеклист

| # | Действие |
|---|----------|
| 1 | Добавить JitPack в settings.gradle.kts и зависимость webrtc:2.0.10 в app/build.gradle.kts |
| 2 | Создать VadSegmentWriter (VAD + буфер сегмента, processFrame, flush, close) |
| 3 | В AudioRecordingService: цикл чтения по 320 сэмплов, вызов processFrame, при сегменте — запись WAV + insert Room |
| 4 | Реализовать запись ShortArray в WAV (заголовок + данные) для сегмента |
| 5 | При остановке сервиса вызывать flush() и сохранить последний сегмент |
| 6 | Проверить на устройстве/эмуляторе: сегменты появляются при речи, не при тишине |
| 7 | Обновить android/README.md (VAD, структура, параметры) |

Итог: после Недели 3 приложение записывает только сегменты с речью, сохраняет их в Room и готово к отправке сегментов на сервер на Неделе 4 (WebSocket).
