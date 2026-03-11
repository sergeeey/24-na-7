# 🧭 **Reflexio v2.1 — "Surpass Smart Noter" Sprint**

**Цель:**

На основе анализа Smart Noter OSINT & Market Intelligence внедрить лучшие практики и устранить их слабые места, чтобы Reflexio стал:

1. быстрее, 2. надёжнее, 3. умнее, 4. прозрачнее.

---

## I. 🔊 ASR Layer — скорость и надёжность транскрипции

**Цель:** сделать Reflexio независимым от сети и устойчивым к шуму.

**Задачи**

1. Добавить в `asr/` новые провайдеры:

   * `whisper-large-v3-turbo` (OpenAI API) для серверного кластерного режима.
   * `distil-whisper` (локальный модуль через CTranslate2) для офлайн режима.
   * `whisperx` для word-timestamps и диаризации спикеров.

2. Интегрировать VAD (WebRTC VAD v2 + adaptive gain control).
3. Проверить форматы (Opus / AAC) и добавить опцию `asr.edge_mode=true`.
4. Метрики успеха:

   * WER ≤ 10 %.
   * Latency < 1 сек.
   * Поддержка офлайн транскрипции ≥ 30 мин без сети.

---

## II. 🧠 LLM & Reasoning Layer — глубина понимания

**Цель:** повысить фактологическую точность и добавить эмоциональный анализ.

**Задачи**

1. Добавить в `summarizer/` модели: `gemini-3-flash`, `gpt-5-mini`, `claude-4.5`.
2. Внедрить Chain-of-Density (CoD) и Few-Shot Action Extraction (JSON формат).
3. Интегрировать эмоциональный анализ (EmoWhisper / pyAudioAnalysis).
4. Реализовать Reflexio-loop (`summarizer → critic → refiner`) с DeepConf метрикой.
5. Метрики:

   * Factual consistency ≥ 98 %.
   * DeepConf score ≥ 0.85.
   * Token entropy ≤ 0.3.

---

## III. 💬 UX Layer — естественное взаимодействие

**Цель:** убрать трение и добавить "волшебство опыта".

**Задачи**

1. Создать PWA `webapp/` с **One-Tap Capture** (MediaRecorder + Supabase upload).
2. Добавить **Smart Replay** (embedding + pgvector + таймкоды).
3. Интегрировать Voiceflow RAG для распознавания интентов и fallback через GPT-mini.
4. Создать вечерний cron (22:50) → `daily_digest.py` → PDF / Telegram дайджест с эмоциями и экшенами.
5. Метрики:

   * старт записи < 300 мс; поиск по аудио < 2 с;
   * accuracy intent ≥ 90 %.

---

## IV. 🧩 Memory & Context Layer — самопамять Reflexio

**Цель:** Reflexio должен помнить контекст, эмоции и привычки пользователя.

**Задачи**

1. Интегрировать Letta SDK в `memory/`:

   * `core_memory.json` — предпочтения пользователя.
   * `session_memory/` — контексты встреч.

2. Добавить self-update памяти через Reflexio-loop (агент обновляет core).
3. Синхронизировать память с дайджестом (добавлять инсайты и паттерны поведения).
4. Метрики:

   * ≥ 70 % саммари не требуют ручной проверки.
   * экономия токенов ≥ 30 %.

---

## V. 🔒 Privacy & Governance Layer — доверие по умолчанию

**Цель:** сделать Reflexio абсолютно безопасным и прозрачным.

**Задачи**

1. Активировать Supabase RLS (`tenant_id == auth.uid()`).
2. Добавить в профиль пользователя флаг `opt_out_training`.
3. Реализовать локальное AES-шифрование в `storage/audio/`.
4. Создать страницу `privacy.md` с Explainable AI («почему модель сделала вывод»).
5. Метрики:

   * 100 % шифрование PII.
   * Zero-retention режим для аудио > 24 ч.

---

## VI. 💰 Monetization & Growth Layer

**Цель:** переплюнуть Smart Noter в монетизации без давления на пользователя.

**Задачи**

1. Ввести Freemium модель: 30 мин в день бесплатно → премиум по минутам.
2. Добавить страницу `pricing.json` и поддержку IAP через Stripe.
3. Сделать Referral систему ("invite 3 → +100 мин").
4. Собрать метрики конверсии → `analytics/monetization.py`.

---

## VII. 📊 Документация и отчётность

**Deliverables**

* `docs/STATUS_REPORT.md` — обновление после спринта.
* `docs/CHANGELOG.md` — новые модули и метрики.
* `docs/privacy.md` — новая политика.
* `Reflexio_Intelligence_Map_v2.md` — новые узлы ASR/LLM/Memory.

---

### ⏱ Сроки и приоритеты (OZERO)

| Фаза                           | Срок    | Приоритет |
| ------------------------------ | ------- | --------- |
| Observe + Zero-Shot (ASR + UX) | 7 дней  | ⚡         |
| Experiment (LLM + Memory)      | 10 дней | 🧠        |
| Result (Privacy + Governance)  | 5 дней  | 🧠        |
| Optimize (Monetization + Docs) | 3 дня   | 🔮        |

---

**Вектор успеха:**

> Smart Noter = "AI-диктофон".  
> Reflexio = "когнитивная операционная система самопонимания".

---

**Дата создания:** 4 ноября 2025  
**Статус:** Планирование

---

## VIII. Reflexio 30/60/90 — From Fragment Pipeline to Episodic Life Memory

### Summary

Главный приоритет на ближайшие 90 дней: не расширять Reflexio в ширину, а довести до зрелости основной memory loop.

Цель:
- перейти от `fragment pipeline` к `episodic life memory`
- сделать `episode` основной единицей памяти
- строить `structured_event`, `digest`, `query`, `commitments`, `graph` в первую очередь от `episode`, а не от одиночного транскрипта
- не хранить весь сырой аудиоархив как продуктовый объект, но и не терять смысл слишком рано на уровне микросегмента

Рабочая формулировка:

> Reflexio уже умеет захватывать, обогащать и частично осмыслять поток жизни, но пока ещё не умеет надёжно собирать его в устойчивые эпизоды, линии и обязательства.

### P0 — Product Truth

Фокус:
- transport reliability
- ASR quality / anti-garbage control
- episode-first memory loop
- digest correctness
- storage truth / reset / reprocess consistency

Уже выполнено:
- добавлены `episodes`
- добавлены `day_threads`
- `episode_id` стал first-class semantic anchor
- `structured_event` уже строится от `episode`
- реализован lifecycle `open -> closed -> summarized`
- реализован finalizer закрытых episodes
- digest переведён на `episode-first`
- digest использует только `summarized episodes`
- transcript fallback помечается как `incomplete_context`
- добавлен post-ASR anti-garbage QC:
  - repeated phrase detector
  - duplicate-neighbor detector
  - mark-for-review
  - quarantine path
- episodic слой покрыт reset/reprocess логикой
- прод уже обновлён на ветку `codex/episodic-memory-pass`

В процессе:
- поздняя фильтрация ещё не полностью вынесена на уровень `episode`
- `day_threads` пока базовые, rule-based
- retrieval/query уже `episode-first`, но ещё не product-grade по качеству ранжирования

Осталось добить:
- доработать late filtering так, чтобы ранние speech/language/privacy gates не убивали значимый контекст слишком рано
- добавить очистку/переклассификацию старых шумных исторических записей
- довести continuity от `day_threads` к месячным `long_threads`
- усилить episode-level contradiction checks и selective second pass для спорных ASR-эпизодов

### P1 — Production Discipline

Фокус:
- CI как обязательный gate
- security posture
- API contract
- observability / SLI / SLO
- release / deploy discipline

Уже выполнено:
- CI разделён на quality / security / build
- добавлены:
  - CodeQL
  - dependency review
  - release workflow
  - OpenAPI export script
- добавлен минимальный `/v1` compatibility layer
- добавлены `CODEOWNERS`
- добавлены issue templates
- prod deploy по episodic ветке уже выполнялся и подтверждён

В процессе:
- API contract начал формализоваться, но ещё не доведён до policy-level
- security gates усилены, но не все claims подтверждены negative tests

Осталось добить:
- deprecation policy и стабильный API versioning contract
- threat model + data flow diagram
- negative security tests:
  - auth
  - upload abuse
  - rate limit
  - reset/admin abuse
  - redaction checks
- SLI/SLO и dashboards:
  - ingest accept rate
  - transcription success rate
  - episode finalization latency
  - digest latency
  - filtered/quarantine rate
- runbooks для деградации transport / ASR / digest

### P2 — Repo / Trust Polish

Фокус:
- repo hygiene
- release discipline
- contributor surface
- external trust signals

Уже выполнено:
- `.gitignore` очищен от части runtime/dev мусора
- добавлены базовые GitHub workflow и issue templates
- OpenAPI можно экспортировать как артефакт

Осталось добить:
- `CHANGELOG.md`
- `CONTRIBUTING.md`
- tagged releases
- release notes discipline
- benchmark section
- golden datasets для ASR / digest / episodes
- reproducible demo scenario
- cleanup исторического tracked мусора из репозитория

### Current Progress

Оценка по слоям:
- `P0`: 75–80 %
- `P1`: 35–40 %
- `P2`: 20–25 %

Самое важное:
- эпизодическая память уже не идея, а работающий слой
- анти-мусорный QC уже встроен
- прод уже обновлён
- новые записи идут через episodic pipeline

### Next Actions

1. Довести `P0` до product-grade:
   - поздняя фильтрация на уровне эпизода
   - selective recheck / second pass
   - очистка старых шумных продовых записей
   - `long_threads` и месячная continuity

2. Закрыть `P1`:
   - threat model
   - negative security tests
   - observability / SLI / SLO / dashboards
   - API policy и deprecation contract

3. Только затем активно закрывать `P2`:
   - changelog / releases
   - docs / contributor surface
   - benchmarks / demo / golden datasets

### Cursor Handoff

Если продолжать работу в Cursor, текущая правильная опорная формула такая:

- **не расширять проект в ширину**
- **сначала довести episodic memory loop**
- **потом production discipline**
- **потом repo/trust polish**

Главный незакрытый разрыв:

> захват уже есть, память как связанный эпизодический слой ещё не доведена до полной зрелости





