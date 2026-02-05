# Voice Autonomy Config

**Источник:** интеграция из Golos (AUTONOMY_CONFIG.md → docs/VOICE_AUTONOMY_CONFIG.md).

## Назначение

Конфигурация автономного режима для голосового захвата и транскрипции в рамках пакета `reflexio`.

## Параметры

- **Захват:** см. `reflexio.audio.AudioRecorder` — `sample_rate`, `frame_duration_ms`, `silence_limit_sec`, `vad_aggressiveness`, `output_dir`.
- **Транскрипция:** см. `reflexio.transcription.WhisperEngine` — использует настройки ASR 24 na 7 (config/asr.yaml, переменные окружения).

## Интеграция с 24 na 7

- Не переопределять глобальные конфиги 24 na 7; при необходимости задавать параметры через переменные окружения или аргументы конструкторов в reflexio.
- При добавлении опций автономии из Golos — дополнять этот документ, не удаляя существующие секции.

---
*При наличии оригинального AUTONOMY_CONFIG.md из Golos его содержимое можно объединить с этим файлом.*
