# 🧭 Reflexio Task Brief — November 2025 Integration Sprint

**Цель:** Ускорить Reflexio 24/7 до production-ready состояния, используя результаты отчёта *Reflexio Intelligence Update (Mid-November 2025)*: обновлённые ASR-модели, улучшенные LLM, метрику DeepConf и систему памяти Letta.

**Сроки:**
- Фаза I–II: 10 дней
- Фаза III–IV: 10 дней
- Фаза V: 5 дней
- Review + merge: 3 дня

---

## I. 🔊 ASR Layer Upgrade

**Цель:** снизить latency и повысить точность транскрипций.

**Задачи:**
1. В `asr/` добавить поддержку:
   - `whisper-large-v3-turbo` (через OpenAI API или локальный inference)
   - `WhisperX` для word-level timestamps и диаризации
2. Добавить опцию `PARAKEET_TDT_V2` (через Modal или Hugging Face) как fallback для длинных аудио
3. В `config/asr.yaml` — новые поля:
   ```yaml
   provider: openai|modal
   model: whisper-v3-turbo|whisperx|parakeet-v2
   diarization: true|false
   timestamps: true
   ```
4. Протестировать pipeline:
   ```bash
   make test-asr-latency
   make test-asr-accuracy
   ```

**Метрика успеха:**
- WER ≤ 10%
- средняя задержка < 1 сек при 44 кГц
- ASR throughput ≥ 5× реального времени

---

## II. 🧠 LLM & Summarization Layer

**Цель:** улучшить качество саммари и reasoning Reflexio-loop.

**Задачи:**
1. В `summarizer/`:
   - добавить опции моделей: `gpt-5-mini`, `gemini-3-flash`, `claude-4.5`
   - реализовать промптинг:
     - `chain_of_density` (CoD)
     - `few_shot_actions` (3 примера JSON-вывода)
2. В `summarizer/critic.py` внедрить `DeepConf`:
   - рассчитывать token-entropy и confidence-score
   - при confidence < 0.85 вызывать refiner-модель (Claude 4.5)
3. Метрики:
   - Factual Consistency ≥ 98%
   - Token Entropy ≤ 0.3
   - Средняя стоимость инференса – 20% ниже текущей

---

## III. 🗣 Voice & UX Layer

**Цель:** дать пользователю быстрый и естественный интерфейс.

**Задачи:**
1. В `webapp/pwa/`:
   - добавить компонент **One-Tap Capture** (MediaRecorder API + upload status)
   - подключить "Smart Replay":
     - хранить embeddings (pgvector) + timestamps из WhisperX
     - добавить поиск по фразам → навигация к таймкоду
2. В `voice_agent/`:
   - интегрировать `Voiceflow RAG` (intent recognition API)
   - протестировать fallback-режим: если RAG недоступен → GPT-mini inference
3. Метрики:
   - время старта записи < 300 мс
   - поиск по аудио < 2 сек
   - точность intent-matching ≥ 90%

---

## IV. 🧩 Memory & Cognitive Layer

**Цель:** сделать Reflexio "помнящим" и самооценивающимся.

**Задачи:**
1. В `memory/`:
   - добавить Letta SDK (Python)
   - реализовать два уровня памяти:
     - `core_memory.json` — предпочтения пользователя
     - `session_memory/` — временные контексты встреч
2. В `loop/`:
   - внедрить DeepConf-score в Reflexio-loop
   - создать pipeline `Summarizer → Critic → Refiner`
3. Метрика:
   - ≥ 70% саммари проходят без ручной проверки
   - Δ стоимости инференса – минус 30%

---

## V. 🔒 Infra / Governance

**Цель:** повысить надёжность и доверие.

**Задачи:**
1. Завершить тесты миграций Supabase + RLS (`tenant_id == auth.uid()`)
2. Добавить флаг `opt_out_training` в профиле пользователя
3. Создать GitHub Actions pipeline:
   - build → test → deploy
   - lint + security scan (Bandit, Ruff)
4. Метрика: 100% тестов CI/CD, zero drift в миграциях

---

## VI. 🧾 Deliverables & Формат отчёта

- `docs/STATUS_REPORT.md` — обновлённый статус после спринта
- `docs/CHANGELOG.md` — новые модели и метрики
- `notebooks/eval/` — latency + quality отчёты (ASR / LLM / DeepConf)
- Обновлённая карта `Reflexio_Intelligence_Map_v2.md`





