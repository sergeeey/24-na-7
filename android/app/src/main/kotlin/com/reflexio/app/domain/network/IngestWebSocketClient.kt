package com.reflexio.app.domain.network

import android.util.Log
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
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
 * WebSocket client for sending audio segments to Reflexio backend.
 * Connects to ws://host/ws/ingest, sends binary WAV, receives "received" then "transcription" or "error".
 * See docs/WEBSOCKET_PROTOCOL.md.
 */
class IngestWebSocketClient(
    private val baseUrl: String = "ws://10.0.2.2:8000"
) {
    private val client = OkHttpClient.Builder()
        .connectTimeout(15, TimeUnit.SECONDS)
        .readTimeout(60, TimeUnit.SECONDS)
        .writeTimeout(30, TimeUnit.SECONDS)
        .build()

    private val wsUrl: String
        get() = baseUrl.removeSuffix("/") + "/ws/ingest"

    /**
     * Sends one WAV file to the server. Returns IngestResult (transcription + fileId) on success.
     * Connects, sends binary, waits for "received" then "transcription" or "error", then closes.
     */
    suspend fun sendSegment(file: File): Result<IngestResult> = withContext(Dispatchers.IO) {
        if (!file.exists()) return@withContext Result.failure(IllegalArgumentException("File not found: ${file.absolutePath}"))
        val bytes = file.readBytes()
        if (bytes.isEmpty()) return@withContext Result.failure(IllegalArgumentException("Empty file"))

        kotlin.runCatching {
            var transcription: String? = null
            var fileId: String? = null
            var error: Throwable? = null
            val latch = java.util.concurrent.CountDownLatch(1)

            val request = Request.Builder().url(wsUrl).build()
            val listener = object : WebSocketListener() {
                override fun onOpen(webSocket: WebSocket, response: Response) {
                    webSocket.send(ByteString.of(*bytes))
                }

                override fun onMessage(webSocket: WebSocket, text: String) {
                    try {
                        val json = JSONObject(text)
                        when (json.optString("type")) {
                            "received" -> {
                                // ПОЧЕМУ сохраняем fileId из "received": это первый ответ
                                // с file_id, нужен для запроса enrichment позже
                                fileId = json.optString("file_id", "").ifEmpty { null }
                            }
                            "transcription" -> {
                                transcription = json.optString("text", "").ifEmpty { null }
                                if (fileId == null) {
                                    fileId = json.optString("file_id", "").ifEmpty { null }
                                }
                                webSocket.close(1000, null)
                                latch.countDown()
                            }
                            "error" -> {
                                error = RuntimeException(json.optString("message", "Unknown error"))
                                webSocket.close(1000, null)
                                latch.countDown()
                            }
                        }
                    } catch (e: Exception) {
                        error = e
                        latch.countDown()
                    }
                }

                override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
                    Log.e(TAG, "WebSocket error", t)
                    error = t
                    latch.countDown()
                }

                override fun onClosing(webSocket: WebSocket, code: Int, reason: String) {
                    latch.countDown()
                }
            }
            client.newWebSocket(request, listener)
            latch.await(90, TimeUnit.SECONDS)
            error?.let { throw it }
            IngestResult(transcription = transcription, fileId = fileId)
        }
    }

    companion object {
        private const val TAG = "IngestWebSocket"
    }
}
