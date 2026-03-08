package com.reflexio.app.domain.network

import android.util.Log
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
import okio.ByteString
import org.json.JSONObject
import java.io.File
import java.util.concurrent.TimeUnit

/**
 * Результат отправки аудио на сервер.
 * ПОЧЕМУ data class а не Pair: явные имена полей вместо .first/.second
 */
data class IngestResult(
    val transcription: String?,
    val fileId: String?,
)

/**
 * WebSocket client с persistent connection и sequential sending.
 *
 * ПОЧЕМУ persistent: каждый новый WebSocket = TCP+TLS handshake (~300ms).
 * При 3-секундных сегментах это 10% overhead. Один WebSocket = send binary → "received" → repeat.
 *
 * ПОЧЕМУ sequential (Mutex): сервер обрабатывает сегменты через IngestWorker очередь.
 * Параллельная отправка не ускоряет — только создаёт contention.
 */
class IngestWebSocketClient(
    private val baseUrl: String = "ws://10.0.2.2:8000",
    private val apiKey: String = "",
) {
    // ПОЧЕМУ один OkHttpClient: connection pooling, один thread pool на все запросы
    private val client = OkHttpClient.Builder()
        .connectTimeout(15, TimeUnit.SECONDS)
        .readTimeout(120, TimeUnit.SECONDS)
        .writeTimeout(30, TimeUnit.SECONDS)
        .pingInterval(30, TimeUnit.SECONDS)  // keep-alive ping
        .build()

    private val wsUrl: String
        get() = baseUrl.removeSuffix("/") + "/ws/ingest"

    private var webSocket: WebSocket? = null
    private var responseChannel: Channel<JSONObject>? = null
    private val connectMutex = Mutex()
    // ПОЧЕМУ sendMutex: гарантирует sequential отправку — один сегмент за раз,
    // следующий ждёт пока предыдущий получит "received"/"transcription"
    private val sendMutex = Mutex()

    /**
     * Подключается к серверу (если ещё нет соединения).
     * Thread-safe через connectMutex.
     */
    private suspend fun ensureConnected(): WebSocket = connectMutex.withLock {
        webSocket?.let { return@withLock it }

        val channel = Channel<JSONObject>(capacity = 16)
        responseChannel = channel

        val request = Request.Builder().url(wsUrl).apply {
            if (apiKey.isNotEmpty()) addHeader("Authorization", "Bearer $apiKey")
        }.build()

        val listener = object : WebSocketListener() {
            override fun onMessage(ws: WebSocket, text: String) {
                try {
                    val json = JSONObject(text)
                    channel.trySend(json)
                } catch (e: Exception) {
                    Log.w(TAG, "Failed to parse message: $text", e)
                }
            }

            override fun onFailure(ws: WebSocket, t: Throwable, response: Response?) {
                Log.e(TAG, "WebSocket connection failed", t)
                disconnect()
            }

            override fun onClosed(ws: WebSocket, code: Int, reason: String) {
                Log.d(TAG, "WebSocket closed: $code $reason")
                disconnect()
            }
        }

        val ws = client.newWebSocket(request, listener)
        webSocket = ws
        ws
    }

    /**
     * Отправляет один WAV файл через persistent WebSocket.
     * Sequential: Mutex гарантирует один сегмент за раз.
     *
     * ПОЧЕМУ fire-and-forget по умолчанию: сервер отвечает "received" мгновенно,
     * транскрипция идёт в фоне. Клиенту достаточно "received" + file_id.
     */
    suspend fun sendSegment(file: File, onStage: ((String) -> Unit)? = null): Result<IngestResult> =
        withContext(Dispatchers.IO) {
            if (!file.exists()) return@withContext Result.failure(
                IllegalArgumentException("File not found: ${file.absolutePath}")
            )
            val bytes = file.readBytes()
            if (bytes.isEmpty()) return@withContext Result.failure(
                IllegalArgumentException("Empty file")
            )

            sendMutex.withLock {
                try {
                    val ws = ensureConnected()
                    val ch = responseChannel ?: return@withLock Result.failure(
                        IllegalStateException("No response channel")
                    )

                    // Отправляем binary
                    val sent = ws.send(ByteString.of(*bytes))
                    if (!sent) {
                        disconnect()
                        return@withLock Result.failure(RuntimeException("WebSocket send failed"))
                    }

                    // Ждём ответы: "received" → "transcription"/"filtered"/"error"
                    var fileId: String? = null
                    var transcription: String? = null

                    // Первый ответ — "received" (мгновенный)
                    val received = withTimeoutOrNull(15_000L) { ch.receive() }
                    if (received == null) {
                        disconnect()
                        return@withLock Result.failure(RuntimeException("Timeout waiting for received"))
                    }

                    when (received.optString("type")) {
                        "received" -> {
                            fileId = received.optString("file_id", "").ifEmpty { null }
                            onStage?.invoke("received")
                        }
                        "error" -> {
                            return@withLock Result.failure(
                                RuntimeException(received.optString("message", "Server error"))
                            )
                        }
                    }

                    // Второй ответ — "transcription"/"filtered" (может занять 30-60 сек)
                    val result = withTimeoutOrNull(90_000L) { ch.receive() }
                    if (result == null) {
                        // Timeout — но "received" был, файл на сервере, enrichment пойдёт
                        return@withLock Result.success(IngestResult(transcription = null, fileId = fileId))
                    }

                    when (result.optString("type")) {
                        "transcription" -> {
                            transcription = result.optString("text", "").ifEmpty { null }
                            if (fileId == null) fileId = result.optString("file_id", "").ifEmpty { null }
                        }
                        "filtered" -> {
                            if (fileId == null) fileId = result.optString("file_id", "").ifEmpty { null }
                        }
                        "error" -> {
                            return@withLock Result.failure(
                                RuntimeException(result.optString("message", "Processing error"))
                            )
                        }
                    }

                    Result.success(IngestResult(transcription = transcription, fileId = fileId))
                } catch (e: Exception) {
                    Log.e(TAG, "sendSegment failed", e)
                    disconnect()
                    Result.failure(e)
                }
            }
        }

    /** Закрыть WebSocket. Вызывается при onFailure/onClosed или явно из сервиса. */
    fun disconnect() {
        webSocket?.close(1000, "client disconnect")
        webSocket = null
        responseChannel?.close()
        responseChannel = null
    }

    companion object {
        private const val TAG = "IngestWebSocket"
    }
}
