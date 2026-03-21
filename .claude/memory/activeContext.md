# Active Context — Reflexio 24/7

## Последнее обновление
2026-03-21

## Текущая фаза
**v1.0 Digital Mirror + Data Access Phases 1-4 — dogfooding active**

## Что сделано в текущей сессии (2026-03-21)
### SSL fix — debug trust anchor (`b371773`, branch fix/ssl-debug-trust-anchor)
- Debug network_security_config.xml не включал isrg_root_x1.pem → CertPathValidatorException на 476 uploads
- Добавлен ISRG Root X1 в debug trust anchors (как в release)
- Добавлен PendingUploadDao.resetAllFailed() + вызов при старте сервиса
- Результат: 0 SSL ошибок, pending uploads дренятся (~10/мин)

### Android UI overhaul (`c4f2090`)
- Dark glassmorphism theme across all 5 tabs (transparent bg, 10% white glass cards)
- Erase Person: GDPR button + confirmation dialog → DELETE /compliance/erase
- Text Note: input на AskScreen → POST /query/note (2-step confirmation token)
- MemoryApi: erasePerson() + postNote() methods
- UI sync from 24-na-7/ clone: People icon, edge-to-edge, navigate-to-record
- NetworkClients: readTimeout 35→120s for /ask LLM calls

### Speaker verification fix (`7d01cb0`)
- threshold 0.75→0.45 (lab-grade → real-world)
- Re-enrollment в шумных условиях (рилсы дочки на фоне)
- Результат: user voice=0.92, TV=0.39 — идеальное разделение
- Deployed на сервер (direct file copy + restart)

### Dogfooding observations
- Pipeline жив: 5154 structured_events, 2451 episodes, 317 long_threads, 2990 memory_nodes
- Телефон: ~3100 recordings, ~1770 с транскрипцией, ~1170 с emotions
- Data Access работает: 29 calendar events, 42 call log entries cached
- Speaker verification теперь узнаёт пользователя (confidence 0.92)

### Quality Gate + Duplicate Text fix (`debcc56`)
- WHERE quality_state='trusted' в mirror, balance, commitments, query fallback
- Enrichment: individual transcription text вместо accumulated episode text
- PersonScreen: фильтр events по имени + кнопка ← назад
- 690 tests passed

### Enrichment prompt fix (`c2b055c`)
- Topics: concrete keywords вместо мета-описаний
- Speakers: extract names when talked ABOUT person

### Все P0 закрыты
- persons: 6 (synced from known_people)
- person_interactions: 4+ (text matching works)
- digest_cache: working (precompute OK)
- .env threshold: 0.45
- DB restored from backup after corruption

### Предыдущие сессии
#### Digital Mirror (feature/v1-digital-mirror, merged to main)
- Android навигация: 5 табов ASK → DAY → PEOPLE → MIRROR → RECORD
- PeopleScreen, MirrorScreen, AskScreen quick actions
- PersonScreen auth fix, MirrorPortrait.avgSentiment nullable fix
- mirror.py sqlcipher fix (get_reflexio_db())

### Data Access Phases (feature/data-access-phases)
- **Phase 1** (`c4e591c`): Contacts + Call Log — ContactsReader, CallLogReader, ContactMatcher, CallRecordingLinker, ContactsPermissionGate, Room migration 4→5
- **Phase 2** (`badfad6`): Calendar — CalendarReader, CachedCalendarEvent, CalendarCacheDao, CalendarPermissionGate, migration 5→6
- **Phase 3** (`badfad6`): Health Connect — HealthConnectReader (sleep/steps/HR), CachedHealthMetric, HealthMetricDao, HealthPermissionGate, migration 6→7
- **Phase 4** (`badfad6`): Geolocation — PassiveLocationTracker (FusedLocation), PlaceResolver (haversine clustering), CachedLocation, LocationCacheDao, LocationPermissionGate, migration 7→8
- Dependencies added: health.connect:connect-client, play-services-location

## Верификация
- Android BUILD SUCCESSFUL (0 errors)
- Python: 674 passed, 24 skipped, 0 failed

## Что осталось
- UI integration: DailySummaryScreen (calendar events, location timeline), MirrorScreen (health metrics)
- Merge feature/data-access-phases → main
- Push + deploy, install APK, dogfooding

## Риски
- Room DB version jump 5→8 requires fresh install (or users on v5 will migrate through 5→6→7→8)
- Health Connect may not be installed on user's phone
- Location permission requires careful UX (показываем только в контексте)

## Auto-commit log
- [2026-03-21 19:07] `771d4d2`: fix: skip enrichment for background speakers (TV, reels, other people)
- [2026-03-21 18:25] `c2b055c`: fix: improve LLM enrichment prompt for topics and speakers extraction
- [2026-03-21 16:59] `debcc56`: fix: add quality gate to analytics, fix duplicate text in enrichment
- [2026-03-21 15:44] `37c8eaf`: feat: wire person_interactions + orchestrator commitments routing
- [2026-03-21 15:23] `7d01cb0`: fix: lower speaker verification threshold 0.75→0.45 for real-world conditions
- [2026-03-21 15:23] `c4f2090`: feat: dark glassmorphism theme, erase person, text note, UI polish
- [2026-03-21 11:22] `b371773`: fix: add ISRG Root X1 to debug network config, reset exhausted uploads
- [2026-03-16 21:26] `2df69f6`: fix: graceful fallback for missing ledger.yaml, mount docs in prod
- [2026-03-16 21:04] `6fd259d`: fix: disable debug localhost pin, add missing prod env vars
- [2026-03-13 23:54] `3ec8be9`: feat: integrate Calendar events in DayScreen, Health metrics in MirrorScreen
- [2026-03-13 23:47] `badfad6`: feat: Phases 2-4 — Calendar, Health Connect, Geolocation integration
- [2026-03-13 23:34] `c4e591c`: feat: Phase 1 — Contacts + Call Log integration
- [2026-03-13 22:46] `2bf9336`: fix: mirror.py use get_reflexio_db() instead of sqlite3.connect()
- [2026-03-13 22:31] `2fe3030`: feat: v1.0 digital mirror — 5-tab navigation, PeopleScreen, MirrorScreen, bug fixes
- [2026-03-12 19:42] `6fc1b85`: fix: remove __future__ annotations breaking admin Pydantic models
