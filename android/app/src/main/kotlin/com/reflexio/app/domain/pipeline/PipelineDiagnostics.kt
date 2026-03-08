package com.reflexio.app.domain.pipeline

import android.content.Context
import android.content.SharedPreferences
import org.json.JSONArray
import org.json.JSONObject

/**
 * Сохраняет последний этап пайплайна и последнюю ошибку для диагностики в UI.
 * Этапы: queued → uploaded → received → transcribed | filtered | error → deleted.
 */
object PipelineDiagnostics {
    private const val PREFS_NAME = "reflexio_pipeline"
    private const val KEY_LAST_STAGE = "last_stage"
    private const val KEY_LAST_ERROR = "last_error"
    private const val KEY_DEBUG_STRIP_VISIBLE = "debug_strip_visible"
    private const val KEY_STAGE_HISTORY = "stage_history"
    private const val KEY_LAST_SERVER_CHECK_AT = "last_server_check_at"
    private const val MAX_HISTORY = 10

    fun prefs(context: Context): SharedPreferences =
        context.applicationContext.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)

    fun setStage(context: Context, stage: String) {
        prefs(context).edit().putString(KEY_LAST_STAGE, stage).apply()
        appendToHistory(context, stage)
    }

    fun setError(context: Context, message: String?) {
        val code = message?.let { normalizeErrorCode(it) }
        prefs(context).edit().putString(KEY_LAST_ERROR, code).apply()
        appendToHistory(context, "error: ${code ?: "unknown"}")
    }

    fun clearError(context: Context) {
        prefs(context).edit().remove(KEY_LAST_ERROR).apply()
    }

    fun getLastStage(context: Context): String? = prefs(context).getString(KEY_LAST_STAGE, null)
    fun getLastError(context: Context): String? = prefs(context).getString(KEY_LAST_ERROR, null)

    /** Режим полоски: true = Debug (полный вид), false = User (одна строка). По умолчанию = BuildConfig.DEBUG. */
    fun getDebugStripVisible(context: Context, defaultFromBuild: Boolean): Boolean =
        prefs(context).getBoolean(KEY_DEBUG_STRIP_VISIBLE, defaultFromBuild)

    fun setDebugStripVisible(context: Context, visible: Boolean) {
        prefs(context).edit().putBoolean(KEY_DEBUG_STRIP_VISIBLE, visible).apply()
    }

    /** Время последней успешной проверки сервера (GET /ingest/pipeline-status). */
    fun setLastServerCheckAt(context: Context, timeMillis: Long) {
        prefs(context).edit().putLong(KEY_LAST_SERVER_CHECK_AT, timeMillis).apply()
    }

    fun getLastServerCheckAt(context: Context): Long? {
        val v = prefs(context).getLong(KEY_LAST_SERVER_CHECK_AT, -1L)
        return if (v < 0) null else v
    }

    /** Кольцевой буфер последних этапов/ошибок для диагностики. Каждый элемент: (timestampMs, label). */
    fun getStageHistory(context: Context): List<Pair<Long, String>> {
        val raw = prefs(context).getString(KEY_STAGE_HISTORY, null) ?: return emptyList()
        return try {
            val arr = JSONArray(raw)
            (0 until arr.length()).map { i ->
                val o = arr.getJSONObject(i)
                o.getLong("t") to o.getString("s")
            }
        } catch (_: Exception) {
            emptyList()
        }
    }

    private fun appendToHistory(context: Context, label: String) {
        val prefs = prefs(context)
        val raw = prefs.getString(KEY_STAGE_HISTORY, "[]") ?: "[]"
        val arr = try { JSONArray(raw) } catch (_: Exception) { JSONArray() }
        arr.put(JSONObject().put("t", System.currentTimeMillis()).put("s", label))
        while (arr.length() > MAX_HISTORY) arr.remove(0)
        prefs.edit().putString(KEY_STAGE_HISTORY, arr.toString()).apply()
    }

    /** Превращает exception message в короткий код для UI. */
    fun normalizeErrorCode(msg: String?): String {
        if (msg.isNullOrBlank()) return "unknown"
        val m = msg.lowercase()
        return when {
            m.contains("timeout") || m.contains("timed out") -> "timeout"
            m.contains("websocket") || m.contains("ws_") || m.contains("closed") -> "ws_closed"
            m.contains("401") || m.contains("unauthorized") || m.contains("auth") -> "auth_failed"
            m.contains("500") || m.contains("internal") -> "server_500"
            m.contains("connection") || m.contains("network") || m.contains("unreachable") -> "network"
            m.contains("ssl") || m.contains("certificate") -> "ssl"
            else -> msg.take(24).replace(Regex("[^a-z0-9_]"), "_")
        }
    }
}
