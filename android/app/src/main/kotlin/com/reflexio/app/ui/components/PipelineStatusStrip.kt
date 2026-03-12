package com.reflexio.app.ui.components

import androidx.compose.foundation.ExperimentalFoundationApi
import androidx.compose.foundation.combinedClickable
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.widget.Toast
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ContentCopy
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.material3.ColorScheme
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp
import com.reflexio.app.BuildConfig
import com.reflexio.app.data.db.RecordingDatabase
import com.reflexio.app.domain.pipeline.PipelineDiagnostics
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.OkHttpClient
import okhttp3.Request
import org.json.JSONObject
import java.util.Calendar
import java.util.concurrent.TimeUnit

private data class PipelineStripData(
    val isDebug: Boolean,
    val pendingCount: Int,
    val processedCount: Int,
    val lastProcessedAt: Long?,
    val lastError: String?,
    val lastStage: String?,
    val serverToday: Int?,
    val serverOk: Boolean?,
    val lastServerCheckAt: Long?,
    /** Код HTTP при ошибке проверки сервера (например 502). */
    val lastServerStatusCode: Int?,
)

/**
 * Мини-статус пайплайна. User mode: одна строка (синхронизация / очередь).
 * Debug mode: полный вид (очередь, отправлено, сервер, этап, ошибка).
 * Long-press по полоске переключает режим (сохраняется в prefs).
 */
@OptIn(ExperimentalFoundationApi::class)
@Composable
fun PipelineStatusStrip(
    baseHttpUrl: String,
    modifier: Modifier = Modifier,
) {
    val context = LocalContext.current.applicationContext
    var pendingCount by remember { mutableStateOf(0) }
    var processedCount by remember { mutableStateOf(0) }
    var lastProcessedAt by remember { mutableStateOf<Long?>(null) }
    var serverToday by remember { mutableStateOf<Int?>(null) }
    var serverOk by remember { mutableStateOf<Boolean?>(null) }
    var lastStage by remember { mutableStateOf<String?>(null) }
    var lastError by remember { mutableStateOf<String?>(null) }
    var isDebugMode by remember { mutableStateOf(false) }
    var refreshTrigger by remember { mutableIntStateOf(0) }
    var isLoading by remember { mutableStateOf(false) }
    var lastServerCheckAt by remember { mutableStateOf<Long?>(null) }
    var lastServerStatusCode by remember { mutableStateOf<Int?>(null) }

    LaunchedEffect(refreshTrigger, baseHttpUrl) {
        isLoading = true
        val result = withContext(Dispatchers.IO) {
            var pCount = 0
            var pProcessed = 0
            var pLastAt: Long? = null
            var pError: String? = null
            var pStage: String? = null
            var pServerToday: Int? = null
            var pServerOk: Boolean? = null
            var pLastServerCheckAt: Long? = PipelineDiagnostics.getLastServerCheckAt(context)
            var pLastServerStatusCode: Int? = null
            try {
                val db = RecordingDatabase.getInstance(context)
                pCount = db.pendingUploadDao().getPendingCount()
                pProcessed = db.recordingDao().getCountByStatus("processed")
                pLastAt = db.recordingDao().getLastProcessedCreatedAt()
                pError = db.pendingUploadDao().getLastFailed()?.lastError?.let {
                    PipelineDiagnostics.normalizeErrorCode(it)
                } ?: PipelineDiagnostics.getLastError(context)
                pStage = PipelineDiagnostics.getLastStage(context)
            } catch (_: Exception) { }
            val url = "${baseHttpUrl.removeSuffix("/")}/ingest/pipeline-status"
            try {
                val client = OkHttpClient.Builder()
                    .connectTimeout(5, TimeUnit.SECONDS)
                    .readTimeout(5, TimeUnit.SECONDS)
                    .build()
                val req = Request.Builder().url(url).apply {
                    if (BuildConfig.SERVER_API_KEY.isNotEmpty()) {
                        addHeader("Authorization", "Bearer ${BuildConfig.SERVER_API_KEY}")
                    }
                }.build()
                client.newCall(req).execute().use { resp ->
                    if (resp.isSuccessful) {
                        val body = resp.body?.string() ?: ""
                        val json = JSONObject(body)
                        pServerToday = json.optInt("transcriptions_today", 0).takeIf { json.has("transcriptions_today") }
                        pServerOk = json.optBoolean("server_ok", true)
                        pLastServerCheckAt = System.currentTimeMillis()
                        PipelineDiagnostics.setLastServerCheckAt(context, pLastServerCheckAt!!)
                    } else {
                        pServerOk = false
                        pLastServerStatusCode = resp.code
                    }
                }
            } catch (_: Exception) {
                pServerOk = false
            }
            PipelineStripData(
                isDebug = PipelineDiagnostics.getDebugStripVisible(context, false),
                pendingCount = pCount,
                processedCount = pProcessed,
                lastProcessedAt = pLastAt,
                lastError = pError,
                lastStage = pStage,
                serverToday = pServerToday,
                serverOk = pServerOk,
                lastServerCheckAt = pLastServerCheckAt,
                lastServerStatusCode = pLastServerStatusCode,
            )
        }
        isDebugMode = result.isDebug
        pendingCount = result.pendingCount
        processedCount = result.processedCount
        lastProcessedAt = result.lastProcessedAt
        lastError = result.lastError
        lastStage = result.lastStage
        serverToday = result.serverToday
        serverOk = result.serverOk
        lastServerCheckAt = result.lastServerCheckAt
        lastServerStatusCode = result.lastServerStatusCode
        isLoading = false
    }


    Column(
        modifier = modifier
            .fillMaxWidth()
            .padding(horizontal = 16.dp, vertical = 4.dp)
            .combinedClickable(
                onLongClick = {
                    isDebugMode = !isDebugMode
                    PipelineDiagnostics.setDebugStripVisible(context, isDebugMode)
                },
                onClick = {},
            ),
    ) {
        if (isDebugMode) {
            DebugStripContent(
                pendingCount = pendingCount,
                processedCount = processedCount,
                serverToday = serverToday,
                serverOk = serverOk,
                lastProcessedAt = lastProcessedAt,
                lastStage = lastStage,
                lastError = lastError,
                lastServerCheckAt = lastServerCheckAt,
                lastServerStatusCode = lastServerStatusCode,
            )
            Row(
                modifier = Modifier.fillMaxWidth(),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                if (isLoading) {
                    CircularProgressIndicator(
                        modifier = Modifier.size(20.dp).padding(end = 8.dp),
                    )
                }
                TextButton(onClick = { refreshTrigger++ }) {
                    Text("Проверить")
                }
                SnapshotCopyButton(
                    context = context,
                    pendingCount = pendingCount,
                    processedCount = processedCount,
                    serverToday = serverToday,
                    lastProcessedAt = lastProcessedAt,
                    lastStage = lastStage,
                    lastError = lastError,
                )
            }
        } else {
            UserStripContent(
                pendingCount = pendingCount,
                lastProcessedAt = lastProcessedAt,
                serverOk = serverOk,
                lastServerStatusCode = lastServerStatusCode,
            )
        }
    }
}

@Composable
private fun UserStripContent(
    pendingCount: Int,
    lastProcessedAt: Long?,
    serverOk: Boolean?,
    lastServerStatusCode: Int? = null,
) {
    val userText = when {
        pendingCount > 0 -> "В очереди $pendingCount записей"
        lastProcessedAt != null -> {
            val minAgo = (System.currentTimeMillis() - lastProcessedAt) / 60_000
            val timeStr = if (minAgo < 1) "только что" else "$minAgo мин назад"
            "Синхронизация в порядке · Последняя обработка $timeStr"
        }
        serverOk == false -> "Сервер перегружен. Данные сохранены локально. Отправка повторится автоматически."
        else -> "Синхронизация в порядке"
    }
    Text(
        text = userText,
        style = MaterialTheme.typography.labelSmall,
        color = MaterialTheme.colorScheme.onSurfaceVariant,
    )
}

@Composable
private fun DebugStripContent(
    pendingCount: Int,
    processedCount: Int,
    serverToday: Int?,
    serverOk: Boolean?,
    lastProcessedAt: Long?,
    lastStage: String?,
    lastError: String?,
    lastServerCheckAt: Long?,
    lastServerStatusCode: Int?,
) {
    val colorScheme = MaterialTheme.colorScheme
    val row1 = buildList {
        add("Очередь: $pendingCount")
        when (val st = serverToday) {
            null -> if (serverOk == false) {
                add(lastServerStatusCode?.let { "Сервер: HTTP $it" } ?: "Сервер: ошибка")
            } else add("Сервер: —")
            else -> add("На сервере сегодня: $st")
        }
        lastServerCheckAt?.let { ts ->
            val c = Calendar.getInstance()
            c.timeInMillis = ts
            add("Проверка: ${String.format("%02d:%02d", c.get(Calendar.HOUR_OF_DAY), c.get(Calendar.MINUTE))}")
        }
    }
    val stageLabel = lastStage?.let { stageToLabel(it) }
    val isSuccessStage = lastStage == "transcribed" || lastStage == "deleted"
    val errorLabel = when {
        lastError == null -> null
        lastStage == "error" -> "Ошибка: $lastError"
        isSuccessStage -> null
        else -> "Ошибка: $lastError"
    }
    val errorColor = if (lastStage == "error") colorScheme.error else colorScheme.outline
    Text(
        text = row1.joinToString("  ·  "),
        style = MaterialTheme.typography.labelSmall,
        color = colorScheme.onSurfaceVariant,
    )
    if (stageLabel != null || lastProcessedAt != null || errorLabel != null) {
        Row(
            modifier = Modifier.padding(top = 2.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            lastProcessedAt?.let { ts ->
                Text(
                    text = "Отправка: ${formatLastSendTime(ts)}",
                    style = MaterialTheme.typography.labelSmall,
                    color = colorScheme.onSurfaceVariant.copy(alpha = 0.85f),
                )
                if (stageLabel != null || errorLabel != null) Text(
                    text = "  ·  ",
                    style = MaterialTheme.typography.labelSmall,
                    color = colorScheme.onSurfaceVariant,
                )
            }
            stageLabel?.let { label ->
                Text(
                    text = "Этап: $label",
                    style = MaterialTheme.typography.labelSmall,
                    color = stageColor(lastStage!!, colorScheme),
                )
                if (errorLabel != null) Text(
                    text = "  ·  ",
                    style = MaterialTheme.typography.labelSmall,
                    color = colorScheme.onSurfaceVariant,
                )
            }
            errorLabel?.let { text ->
                Text(
                    text = text,
                    style = MaterialTheme.typography.labelSmall,
                    color = errorColor.copy(alpha = if (isSuccessStage) 0.7f else 1f),
                )
            }
        }
    }
}

private fun formatHistoryTime(ts: Long): String {
    val c = Calendar.getInstance()
    c.timeInMillis = ts
    return String.format("%02d:%02d", c.get(Calendar.HOUR_OF_DAY), c.get(Calendar.MINUTE))
}

@OptIn(ExperimentalFoundationApi::class)
@Composable
private fun SnapshotCopyButton(
    context: Context,
    pendingCount: Int,
    processedCount: Int,
    serverToday: Int?,
    lastProcessedAt: Long?,
    lastStage: String?,
    lastError: String?,
) {
    IconButton(
        modifier = Modifier.combinedClickable(
            onClick = {
                val lastStr = lastProcessedAt?.let { formatLastSendTime(it) } ?: "-"
                val sStr = serverToday?.toString() ?: "-"
                val stageStr = lastStage ?: "-"
                val errStr = lastError ?: "-"
                val snapshot = "Q=$pendingCount | P=$processedCount | S=$sStr | Last=$lastStr | Stage=$stageStr | Err=$errStr"
                val cm = context.getSystemService(Context.CLIPBOARD_SERVICE) as? ClipboardManager
                cm?.setPrimaryClip(ClipData.newPlainText("reflexio-pipeline", snapshot))
                Toast.makeText(context, "Снимок пайплайна скопирован", Toast.LENGTH_SHORT).show()
            },
            onLongClick = {
                val lastStr = lastProcessedAt?.let { formatLastSendTime(it) } ?: "-"
                val sStr = serverToday?.toString() ?: "-"
                val stageStr = lastStage ?: "-"
                val errStr = lastError ?: "-"
                val snapshot = "Q=$pendingCount | P=$processedCount | S=$sStr | Last=$lastStr | Stage=$stageStr | Err=$errStr"
                val history = PipelineDiagnostics.getStageHistory(context)
                    .joinToString("\n") { (ts, label) -> "${formatHistoryTime(ts)} $label" }
                val full = if (history.isEmpty()) snapshot else "$snapshot\n\nИстория:\n$history"
                val cm = context.getSystemService(Context.CLIPBOARD_SERVICE) as? ClipboardManager
                cm?.setPrimaryClip(ClipData.newPlainText("reflexio-pipeline", full))
                Toast.makeText(context, "Снимок и история скопированы", Toast.LENGTH_SHORT).show()
            },
        ),
        onClick = {},
    ) {
        Icon(Icons.Default.ContentCopy, contentDescription = "Копировать снимок; долгое нажатие — с историей")
    }
}

private fun stageColor(stage: String, colorScheme: ColorScheme): Color = when (stage) {
    "queued" -> colorScheme.tertiary
    "uploaded", "received" -> colorScheme.primary
    "transcribed" -> colorScheme.primary
    "filtered", "deleted" -> colorScheme.outline
    "error" -> colorScheme.error
    else -> colorScheme.onSurfaceVariant
}

private fun stageToLabel(stage: String): String = when (stage) {
    "queued" -> "в очереди"
    "uploaded" -> "отправка"
    "received" -> "принято"
    "transcribed" -> "обработано"
    "filtered" -> "отфильтровано"
    "deleted" -> "удалён"
    "error" -> "ошибка"
    else -> stage
}

private fun formatLastSendTime(createdAtMillis: Long): String {
    val c = Calendar.getInstance()
    c.timeInMillis = createdAtMillis
    val today = Calendar.getInstance()
    return when {
        c.get(Calendar.YEAR) == today.get(Calendar.YEAR) &&
            c.get(Calendar.DAY_OF_YEAR) == today.get(Calendar.DAY_OF_YEAR) ->
            String.format("%02d:%02d", c.get(Calendar.HOUR_OF_DAY), c.get(Calendar.MINUTE))
        c.get(Calendar.YEAR) == today.get(Calendar.YEAR) &&
            c.get(Calendar.DAY_OF_YEAR) == today.get(Calendar.DAY_OF_YEAR) - 1 ->
            "вч ${String.format("%02d:%02d", c.get(Calendar.HOUR_OF_DAY), c.get(Calendar.MINUTE))}"
        else ->
            String.format("%td.%tm %02d:%02d", c, c, c.get(Calendar.HOUR_OF_DAY), c.get(Calendar.MINUTE))
    }
}
