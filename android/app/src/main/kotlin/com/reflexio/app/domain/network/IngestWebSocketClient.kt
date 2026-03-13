package com.reflexio.app.domain.network

import android.util.Log
import android.util.Base64
import android.util.Base64OutputStream
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.withContext
import kotlinx.coroutines.withTimeoutOrNull
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import org.json.JSONObject
import java.io.ByteArrayOutputStream
import java.io.File

/**
 * Результат отправки аудио на сервер.
 * ПОЧЕМУ data class а не Pair: явные имена полей вместо .first/.second
 */
data class IngestResult(
    val transcription: String?,
    val fileId: String?,
    val ackStatus: String?,
)

/**
 * WebSocket client с изолированной сессией на каждый сегмент и sequential sending.
 *
 * ПОЧЕМУ отдельная сессия: мобильная сеть и background lifecycle чаще ломают shared
 * socket/channel state, чем сам handshake. Один сегмент = одна чистая сессия =
 * меньше гонок и ложных "channel closed" / "no response channel".
 *
 * ПОЧЕМУ sequential (Mutex): сервер обрабатывает сегменты через IngestWorker очередь.
 * Параллельная отправка не ускоряет — только создаёт contention.
 */
class IngestWebSocketClient(
    private val baseUrl: String = "ws://10.0.2.2:8000",
    private val apiKey: String = "",
) {
    // ПОЧЕМУ shared client: не плодим TCP/thread pools на каждый worker/service.
    private val client = NetworkClients.sharedClient

    private val wsUrl: String
        get() = baseUrl.removeSuffix("/") + "/ws/ingest"

    // ПОЧЕМУ sendMutex: гарантирует sequential отправку — один сегмент за раз,
    // следующий ждёт пока предыдущий получит "received"/"transcription"
    private val sendMutex = Mutex()
    @Volatile
    private var activeSocket: WebSocket? = null
    @Volatile
    private var activeChannel: Channel<JSONObject>? = null

    private fun openSession(): Session {
        val channel = Channel<JSONObject>(capacity = 16)
        val openSignal = CompletableDeferred<Unit>()
        Log.d(TAG, "Opening websocket session baseUrl=$baseUrl wsUrl=$wsUrl")
        val request = Request.Builder().url(wsUrl).apply {
            if (apiKey.isNotEmpty()) addHeader("Authorization", "Bearer $apiKey")
        }.build()

        val listener = object : WebSocketListener() {
            override fun onOpen(webSocket: WebSocket, response: Response) {
                Log.d(TAG, "WebSocket opened")
                if (!openSignal.isCompleted) {
                    openSignal.complete(Unit)
                }
            }

            override fun onMessage(webSocket: WebSocket, text: String) {
                try {
                    val json = JSONObject(text)
                    channel.trySend(json)
                } catch (e: Exception) {
                    Log.w(TAG, "Failed to parse message: $text", e)
                }
            }

            override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
                Log.e(TAG, "WebSocket connection failed", t)
                if (!openSignal.isCompleted) {
                    openSignal.completeExceptionally(t)
                }
                channel.close(t)
                clearActiveSession(webSocket, channel)
            }

            override fun onClosed(webSocket: WebSocket, code: Int, reason: String) {
                Log.d(TAG, "WebSocket closed: $code $reason")
                if (!openSignal.isCompleted) {
                    openSignal.completeExceptionally(
                        IllegalStateException("WebSocket closed before open: $code $reason")
                    )
                }
                channel.close()
                clearActiveSession(webSocket, channel)
            }
        }

        val ws = client.newWebSocket(request, listener)
        activeSocket = ws
        activeChannel = channel
        return Session(ws, channel, openSignal)
    }

    /**
     * Отправляет один WAV файл через persistent WebSocket.
     * Sequential: Mutex гарантирует один сегмент за раз.
     *
     * ПОЧЕМУ fire-and-forget по умолчанию: сервер отвечает "received" мгновенно,
     * транскрипция идёт в фоне. Клиенту достаточно "received" + file_id.
     */
    suspend fun sendSegment(
        file: File,
        segmentId: String? = null,
        capturedAt: Long? = null,
        onStage: ((String) -> Unit)? = null,
    ): Result<IngestResult> =
        withContext(Dispatchers.IO) {
            if (!file.exists()) return@withContext Result.failure(
                IllegalArgumentException("File not found: ${file.absolutePath}")
            )
            val payload = encodeFileAsBase64(file)
            if (payload.isEmpty()) return@withContext Result.failure(
                IllegalArgumentException("Empty file")
            )

            sendMutex.withLock {
                var lastError: Throwable? = null
                repeat(2) { attempt ->
                    val result = sendSegmentUntilReceived(payload, segmentId, capturedAt, onStage)
                    if (result.isSuccess) {
                        return@withLock result
                    }
                    val error = result.exceptionOrNull()
                    lastError = error
                    if (attempt == 0 && shouldRetryTransportFailure(error)) {
                        Log.w(TAG, "Retrying WebSocket send after transient failure: ${error?.message}")
                        disconnect()
                    } else {
                        return@withLock result
                    }
                }
                Result.failure(lastError ?: RuntimeException("Upload failed"))
            }
        }

    private suspend fun sendSegmentUntilReceived(
        base64Payload: String,
        segmentId: String?,
        capturedAt: Long?,
        onStage: ((String) -> Unit)?,
    ): Result<IngestResult> {
        var session: Session? = null
        return try {
            session = openSession()
            val ws = session.webSocket
            val ch = session.channel
            val opened = withTimeoutOrNull(5_000L) { session.openSignal.await() }
            if (opened == null) {
                return Result.failure(RuntimeException("Timeout waiting for websocket open"))
            }

            val requestPayload = JSONObject().apply {
                put("type", "audio")
                put("data", base64Payload)
                if (!segmentId.isNullOrBlank()) put("segment_id", segmentId)
                if (capturedAt != null) put("captured_at", capturedAt)
            }
            val sent = ws.send(requestPayload.toString())
            if (!sent) {
                return Result.failure(RuntimeException("WebSocket send failed"))
            }

            var fileId: String?
            var ackStatus: String?

            val receivedResult = withTimeoutOrNull(20_000L) { ch.receiveCatching() }
            if (receivedResult == null) {
                return Result.failure(RuntimeException("Timeout waiting for received"))
            }
            val received = receivedResult.getOrNull()
                ?: return Result.failure(RuntimeException("Channel was closed"))

            when (received.optString("type")) {
                "received" -> {
                    fileId = received.optString("file_id", "").ifEmpty { null }
                    ackStatus = received.optString("status", "").ifEmpty { null }
                    onStage?.invoke("received")
                }
                "error" -> {
                    return Result.failure(
                        RuntimeException(received.optString("message", "Server error"))
                    )
                }
                else -> {
                    return Result.failure(
                        RuntimeException("Unexpected server response: ${received.optString("type")}")
                    )
                }
            }
            Result.success(IngestResult(transcription = null, fileId = fileId, ackStatus = ackStatus))
        } catch (e: Exception) {
            Log.e(TAG, "sendSegment failed", e)
            Result.failure(e)
        } finally {
            session?.let { closeSession(it, "segment complete") }
        }
    }

    private fun shouldRetryTransportFailure(error: Throwable?): Boolean {
        val message = error?.message?.lowercase() ?: return false
        return message.contains("websocket send failed") ||
            message.contains("channel was closed") ||
            message.contains("timeout waiting for received") ||
            message.contains("timeout waiting for websocket open") ||
            message.contains("no response channel")
    }

    /** Закрыть WebSocket. Вызывается при onFailure/onClosed или явно из сервиса. */
    fun disconnect() {
        activeSocket?.close(1000, "client disconnect")
        activeChannel?.close()
        activeSocket = null
        activeChannel = null
    }

    private fun closeSession(session: Session, reason: String) {
        session.webSocket.close(1000, reason)
        session.channel.close()
        clearActiveSession(session.webSocket, session.channel)
    }

    private fun clearActiveSession(webSocket: WebSocket, channel: Channel<JSONObject>) {
        if (activeSocket === webSocket) activeSocket = null
        if (activeChannel === channel) activeChannel = null
    }

    private data class Session(
        val webSocket: WebSocket,
        val channel: Channel<JSONObject>,
        val openSignal: CompletableDeferred<Unit>,
    )

    companion object {
        private const val TAG = "IngestWebSocket"
    }

    private fun encodeFileAsBase64(file: File): String {
        val output = ByteArrayOutputStream((file.length() * 1.4).toInt().coerceAtLeast(1024))
        Base64OutputStream(output, Base64.NO_WRAP).use { base64Stream ->
            file.inputStream().use { input ->
                val buffer = ByteArray(64 * 1024)
                while (true) {
                    val read = input.read(buffer)
                    if (read <= 0) break
                    base64Stream.write(buffer, 0, read)
                }
            }
        }
        return output.toString(Charsets.US_ASCII.name())
    }
}
