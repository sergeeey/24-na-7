# WebSocket protocol: ingest audio (Week 4)

Endpoint: `GET /ws/ingest` (upgrade to WebSocket).

## Connection

- URL: `ws://<host>:<port>/ws/ingest` (or `wss://` for TLS).
- No query parameters required. Optional: client/device id in future.

## Client → Server

1. **Binary frame:** raw WAV bytes. Server saves to `UPLOADS_PATH` as `{timestamp}_{file_id}.wav`, returns `received` then runs transcription and sends `transcription` or `error`.

2. **Text frame (JSON):**
   - `{ "type": "audio", "data": "<base64-encoded WAV>" }` — same as binary, server saves and processes.

## Server → Client

All messages are JSON text frames:

- `{ "type": "received", "file_id": "<uuid>", "status": "queued", "filename": "<name>.wav" }` — file saved.
- `{ "type": "transcription", "file_id": "<uuid>", "text": "...", "language": "..." }` — transcription ready.
- `{ "type": "error", "file_id": "<uuid>", "message": "..." }` or `{ "type": "error", "message": "..." }` — error.

## Flow

1. Client connects to `/ws/ingest`.
2. Client sends one or more audio segments (binary or JSON with base64).
3. For each segment, server responds with `received`, then (after transcribe) `transcription` or `error`.
4. Client can update local state (e.g. Room) with `file_id`, `text`, or error.

## Limits

- Message size: consider limiting (e.g. 5 MB) to avoid DoS.
- Rate limiting: same as REST ingest where applicable.

## Android client

- **Endpoint:** `IngestWebSocketClient(baseUrl)` → connects to `baseUrl/ws/ingest`.
- **URL задаётся через BuildConfig** (`app/build.gradle.kts`):
  - **debug:** эмулятор — `SERVER_WS_URL = ws://10.0.2.2:8000`; реальное устройство — `SERVER_WS_URL_DEVICE = ws://192.168.1.100:8000` (подставьте IP вашего ПК).
  - **release:** `SERVER_WS_URL` / `SERVER_WS_URL_DEVICE` — заменить на `wss://api.reflexio.example.com` перед выкладкой.
- Эмулятор определяется автоматически (FINGERPRINT/MODEL), на устройстве используется `SERVER_WS_URL_DEVICE`.
- **Flow:** VAD segments → WAV → binary frames → `received` → `transcription`/`error` → обновление Room и UI.
