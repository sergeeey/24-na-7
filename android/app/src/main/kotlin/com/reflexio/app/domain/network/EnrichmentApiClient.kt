package com.reflexio.app.domain.network

import android.util.Log
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.OkHttpClient
import okhttp3.Request
import org.json.JSONObject
import java.util.concurrent.TimeUnit

/**
 * HTTP клиент для получения enrichment данных (summary, emotions, topics, tasks).
 *
 * ПОЧЕМУ OkHttp а не Retrofit: у нас 1 endpoint, Retrofit — overkill.
 * OkHttp уже в зависимостях для WebSocket.
 */
class EnrichmentApiClient(
    private val baseUrl: String = "http://10.0.2.2:8000"
) {
    private val client = OkHttpClient.Builder()
        .connectTimeout(10, TimeUnit.SECONDS)
        .readTimeout(15, TimeUnit.SECONDS)
        .build()

    /**
     * Запрашивает enrichment данные для записи по серверному file_id.
     * Возвращает null если enrichment ещё не готов (404) или произошла ошибка.
     */
    suspend fun fetchEnrichment(fileId: String): EnrichmentData? = withContext(Dispatchers.IO) {
        try {
            val url = "${baseUrl.removeSuffix("/")}/enrichment/by-ingest/$fileId"
            val request = Request.Builder().url(url).get().build()
            val response = client.newCall(request).execute()

            if (!response.isSuccessful) {
                Log.d(TAG, "Enrichment not ready for $fileId: ${response.code}")
                return@withContext null
            }

            val body = response.body?.string() ?: return@withContext null
            val json = JSONObject(body)

            if (json.optString("status") != "enriched") {
                return@withContext null
            }

            val data = json.optJSONObject("data") ?: return@withContext null
            EnrichmentData(
                summary = data.optString("summary", "").ifEmpty { null },
                emotions = data.optJSONArray("emotions")?.let { arr ->
                    (0 until arr.length()).map { arr.getString(it) }
                } ?: emptyList(),
                topics = data.optJSONArray("topics")?.let { arr ->
                    (0 until arr.length()).map { arr.getString(it) }
                } ?: emptyList(),
                tasks = data.optJSONArray("tasks")?.toString(),
                urgency = data.optString("urgency", "medium").ifEmpty { "medium" },
                sentiment = data.optString("sentiment", "neutral").ifEmpty { "neutral" },
            )
        } catch (e: Exception) {
            Log.w(TAG, "Failed to fetch enrichment for $fileId", e)
            null
        }
    }

    companion object {
        private const val TAG = "EnrichmentApi"
    }
}

/**
 * Enrichment данные от сервера.
 * ПОЧЕМУ отдельный data class а не часть Recording:
 * это промежуточная структура для парсинга JSON → Recording update.
 */
data class EnrichmentData(
    val summary: String?,
    val emotions: List<String>,
    val topics: List<String>,
    val tasks: String?,       // JSON string for storage in Room
    val urgency: String,
    val sentiment: String,
)
