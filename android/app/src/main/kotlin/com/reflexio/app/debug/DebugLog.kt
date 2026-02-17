package com.reflexio.app.debug

import android.util.Log
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL

/**
 * Отправка NDJSON логов на хост для отладки (эмулятор: 10.0.2.2).
 * Регионы agent log — не удалять до верификации.
 */
object DebugLog {
    private const val TAG = "RFLX_DBG"
    private const val INGEST_URL = "http://10.0.2.2:7245/ingest/66a35078-c564-4475-82a0-106b401b1bfc"

    // #region agent log
    fun log(hypothesisId: String, location: String, message: String, data: Map<String, Any?> = emptyMap()) {
        val payload = JSONObject().apply {
            put("sessionId", "debug-session")
            put("runId", "run1")
            put("hypothesisId", hypothesisId)
            put("location", location)
            put("message", message)
            put("data", data.toString())
            put("timestamp", System.currentTimeMillis())
        }.toString()
        Log.d(TAG, "HYP_$hypothesisId|$location|$message|$data")
        Thread {
            try {
                val conn = URL(INGEST_URL).openConnection() as HttpURLConnection
                conn.requestMethod = "POST"
                conn.setRequestProperty("Content-Type", "application/json")
                conn.doOutput = true
                conn.connectTimeout = 2000
                conn.readTimeout = 2000
                conn.outputStream.use { it.write(payload.toByteArray(Charsets.UTF_8)) }
                val code = conn.responseCode
                if (code !in 200..299) Log.w(TAG, "ingest response $code")
            } catch (e: Exception) {
                Log.w(TAG, "ingest failed", e)
            }
        }.start()
    }
    // #endregion
}
