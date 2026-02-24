package com.reflexio.app.ui.screens

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material3.AssistChip
import androidx.compose.material3.AssistChipDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.reflexio.app.BuildConfig
import com.reflexio.app.ui.components.ActionItemCard
import com.reflexio.app.ui.components.DigestShimmerSkeleton
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.OkHttpClient
import okhttp3.Request
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import java.util.concurrent.TimeUnit

// ПОЧЕМУ полный редизайн:
// Было: плоский текст с "□"/"✓" перед задачами — как блокнот из 2005.
// Стало: FlowRow чипсы (Ambi), интерактивные задачи (Omi), shimmer loading, прогресс-кольцо.
// Аналогия из security: UI — это "фасад" продукта, как reception в банке.
// Сильный бэкенд без хорошего UI — как банк с бронированным хранилищем, но без входной двери.

private val ColorTeal = Color(0xFF00E5CC)
private val ColorIndigo = Color(0xFF7C6CFF)
private val ColorAmber = Color(0xFFFFB74D)

/**
 * Экран «Итог дня»: загружает GET /digest/daily?date= и отображает
 * summary, темы (FlowRow chips), эмоции, интерактивные задачи.
 */
@Composable
fun DailySummaryScreen(
    onBack: () -> Unit,
    modifier: Modifier = Modifier,
    baseHttpUrl: String,
) {
    var loading by remember { mutableStateOf(true) }
    var error by remember { mutableStateOf<String?>(null) }
    var data by remember { mutableStateOf<DailyDigestData?>(null) }
    var retryCount by remember { mutableStateOf(0) }

    val today = SimpleDateFormat("yyyy-MM-dd", Locale.US).format(Date())

    LaunchedEffect(baseHttpUrl, today, retryCount) {
        loading = true
        error = null
        data = null
        val result = withContext(Dispatchers.IO) {
            fetchDailyDigest(baseHttpUrl, today)
        }
        loading = false
        when (result) {
            is DailyDigestResult.Success -> data = result.data
            is DailyDigestResult.Error -> error = result.message
        }
    }

    Column(modifier = modifier.fillMaxSize().padding(16.dp)) {
        // Header
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Text("Итог дня", style = MaterialTheme.typography.titleLarge)
            IconButton(onClick = { retryCount++ }) {
                Icon(
                    Icons.Default.Refresh,
                    contentDescription = "Обновить",
                    tint = MaterialTheme.colorScheme.primary,
                )
            }
        }
        Spacer(modifier = Modifier.height(8.dp))

        when {
            loading -> {
                // ПОЧЕМУ shimmer: скелетная загрузка вместо спиннера снижает
                // perceived wait time — пользователь видит форму будущего контента.
                DigestShimmerSkeleton()
            }
            error != null -> {
                ErrorState(error = error!!, onRetry = { retryCount++ })
            }
            data != null -> {
                DailySummaryContent(data = data!!)
            }
        }
    }
}

@Composable
private fun ErrorState(error: String, onRetry: () -> Unit) {
    Column(
        modifier = Modifier.fillMaxSize(),
        verticalArrangement = Arrangement.Center,
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Text(
            text = if (error.contains("HTTP 404") || error.contains("no_recordings"))
                "Сегодня записей пока нет"
            else
                "Ошибка: $error",
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.outline,
        )
        Spacer(modifier = Modifier.height(12.dp))
        IconButton(onClick = onRetry) {
            Icon(Icons.Default.Refresh, contentDescription = "Повторить", tint = ColorTeal)
        }
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun DailySummaryContent(data: DailyDigestData) {
    val scroll = rememberScrollState()
    // ПОЧЕМУ mutableStateListOf: нужно отслеживать какие задачи пользователь отметил.
    // remember { data.actions.map { false }.toMutableStateList() } создаёт
    // observable список — Compose перерисует только изменённые карточки.
    val completedStates = remember { mutableStateListOf(*BooleanArray(data.actions.size) { data.actions[it].done }.toTypedArray()) }

    Column(modifier = Modifier.verticalScroll(scroll)) {
        // === Summary ===
        data.summary_text.takeIf { it.isNotBlank() }?.let { summary ->
            SectionHeader("Итог")
            Card(
                modifier = Modifier.fillMaxWidth(),
                colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant),
            ) {
                Text(
                    text = summary,
                    style = MaterialTheme.typography.bodyMedium,
                    modifier = Modifier.padding(12.dp),
                    lineHeight = 20.sp,
                )
            }
            Spacer(modifier = Modifier.height(20.dp))
        }

        // === Themes (FlowRow chips) ===
        if (data.key_themes.isNotEmpty()) {
            SectionHeader("Ключевые темы")
            FlowRow(
                horizontalArrangement = Arrangement.spacedBy(8.dp),
                verticalArrangement = Arrangement.spacedBy(4.dp),
            ) {
                data.key_themes.forEach { theme ->
                    AssistChip(
                        onClick = { },
                        label = { Text(theme, style = MaterialTheme.typography.labelMedium) },
                        colors = AssistChipDefaults.assistChipColors(
                            containerColor = ColorIndigo.copy(alpha = 0.15f),
                            labelColor = ColorIndigo,
                        ),
                        border = null,
                    )
                }
            }
            Spacer(modifier = Modifier.height(20.dp))
        }

        // === Emotions (FlowRow chips) ===
        if (data.emotions.isNotEmpty()) {
            SectionHeader("Эмоции")
            FlowRow(
                horizontalArrangement = Arrangement.spacedBy(8.dp),
                verticalArrangement = Arrangement.spacedBy(4.dp),
            ) {
                data.emotions.forEach { emotion ->
                    AssistChip(
                        onClick = { },
                        label = { Text(emotion, style = MaterialTheme.typography.labelMedium) },
                        colors = AssistChipDefaults.assistChipColors(
                            containerColor = ColorAmber.copy(alpha = 0.15f),
                            labelColor = ColorAmber,
                        ),
                        border = null,
                    )
                }
            }
            Spacer(modifier = Modifier.height(20.dp))
        }

        // === Actions (interactive cards + progress ring) ===
        if (data.actions.isNotEmpty()) {
            val completedCount = completedStates.count { it }
            val totalCount = data.actions.size

            Row(
                verticalAlignment = Alignment.CenterVertically,
                modifier = Modifier.padding(bottom = 8.dp),
            ) {
                // ПОЧЕМУ CircularProgressIndicator: визуализация прогресса
                // мотивирует завершать задачи (gamification loop).
                // Аналогия: как прогресс-бар при загрузке файла — видишь сколько осталось.
                GoalProgressRing(completed = completedCount, total = totalCount)
                Spacer(modifier = Modifier.width(12.dp))
                Column {
                    Text(
                        "Намерения дня",
                        style = MaterialTheme.typography.titleMedium,
                        fontWeight = FontWeight.SemiBold,
                    )
                    Text(
                        "Выполнено $completedCount из $totalCount",
                        style = MaterialTheme.typography.bodySmall,
                        color = if (completedCount == totalCount) ColorTeal
                               else MaterialTheme.colorScheme.outline,
                    )
                }
            }

            data.actions.forEachIndexed { index, action ->
                ActionItemCard(
                    taskText = action.text,
                    urgency = action.urgency,
                    isCompleted = completedStates[index],
                    onToggle = { checked -> completedStates[index] = checked },
                )
            }
            Spacer(modifier = Modifier.height(20.dp))
        }

        // === Statistics ===
        SectionHeader("Статистика")
        Card(
            modifier = Modifier.fillMaxWidth(),
            colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant),
        ) {
            Row(
                modifier = Modifier.padding(12.dp).fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceEvenly,
            ) {
                StatItem(label = "Записей", value = "${data.total_recordings}")
                StatItem(label = "Длительность", value = data.total_duration)
            }
        }

        // === Repetitions ===
        if (data.repetitions.isNotEmpty()) {
            Spacer(modifier = Modifier.height(20.dp))
            SectionHeader("Повторяется")
            data.repetitions.forEach { rep ->
                Text(
                    "• $rep",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.outline,
                    modifier = Modifier.padding(vertical = 2.dp),
                )
            }
        }

        // Bottom spacing for navigation bar
        Spacer(modifier = Modifier.height(16.dp))
    }
}

@Composable
private fun SectionHeader(title: String) {
    Text(
        text = title,
        style = MaterialTheme.typography.titleMedium,
        fontWeight = FontWeight.SemiBold,
        modifier = Modifier.padding(bottom = 8.dp),
    )
}

@Composable
private fun StatItem(label: String, value: String) {
    Column(horizontalAlignment = Alignment.CenterHorizontally) {
        Text(
            text = value,
            style = MaterialTheme.typography.titleMedium,
            color = ColorTeal,
            fontWeight = FontWeight.Bold,
        )
        Text(
            text = label,
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.outline,
        )
    }
}

/**
 * Кольцо прогресса выполнения задач.
 * Показывает completed/total как CircularProgressIndicator + иконку в центре.
 */
@Composable
private fun GoalProgressRing(completed: Int, total: Int) {
    val progress = if (total > 0) completed.toFloat() / total else 0f
    val allDone = completed == total && total > 0

    Box(
        contentAlignment = Alignment.Center,
        modifier = Modifier.size(48.dp),
    ) {
        // Background track
        @Suppress("DEPRECATION")
        CircularProgressIndicator(
            progress = 1f,
            modifier = Modifier.size(48.dp),
            color = MaterialTheme.colorScheme.outline.copy(alpha = 0.2f),
            strokeWidth = 4.dp,
        )
        // Progress arc
        @Suppress("DEPRECATION")
        CircularProgressIndicator(
            progress = progress,
            modifier = Modifier.size(48.dp),
            color = if (allDone) ColorTeal else ColorIndigo,
            strokeWidth = 4.dp,
        )
        // Center icon or text
        if (allDone) {
            Icon(
                Icons.Default.CheckCircle,
                contentDescription = "Все выполнено",
                tint = ColorTeal,
                modifier = Modifier.size(20.dp),
            )
        } else {
            Text(
                text = "$completed",
                style = MaterialTheme.typography.labelMedium,
                fontWeight = FontWeight.Bold,
                color = ColorIndigo,
            )
        }
    }
}

// === Data classes ===

private data class DailyDigestData(
    val date: String,
    val summary_text: String,
    val key_themes: List<String>,
    val emotions: List<String>,
    val actions: List<ActionItem>,
    val total_recordings: Int,
    val total_duration: String,
    val repetitions: List<String>,
)

private data class ActionItem(
    val text: String,
    val done: Boolean,
    val urgency: String = "medium",
)

private sealed class DailyDigestResult {
    data class Success(val data: DailyDigestData) : DailyDigestResult()
    data class Error(val message: String) : DailyDigestResult()
}

private fun fetchDailyDigest(baseHttpUrl: String, date: String): DailyDigestResult {
    val url = "$baseHttpUrl/digest/daily?date=$date".replace("//digest", "/digest")
    val client = OkHttpClient.Builder()
        .connectTimeout(15, TimeUnit.SECONDS)
        .readTimeout(30, TimeUnit.SECONDS)
        .build()
    return try {
        val requestBuilder = Request.Builder().url(url).get()
        // ПОЧЕМУ auth header: после security fix (auth_middleware) все endpoints
        // кроме /health и / требуют Bearer token. Без этого — 401.
        val apiKey = BuildConfig.SERVER_API_KEY
        if (apiKey.isNotEmpty()) {
            requestBuilder.addHeader("Authorization", "Bearer $apiKey")
        }
        val request = requestBuilder.build()
        val response = client.newCall(request).execute()
        if (!response.isSuccessful) {
            return DailyDigestResult.Error("HTTP ${response.code}")
        }
        val body = response.body?.string() ?: return DailyDigestResult.Error("Empty response")
        val json = org.json.JSONObject(body)
        val keyThemes = mutableListOf<String>()
        val jaThemes = json.optJSONArray("key_themes")
        if (jaThemes != null) for (i in 0 until jaThemes.length()) keyThemes.add(jaThemes.optString(i, ""))
        val emotions = mutableListOf<String>()
        val jaEmotions = json.optJSONArray("emotions")
        if (jaEmotions != null) for (i in 0 until jaEmotions.length()) emotions.add(jaEmotions.optString(i, ""))
        val actions = mutableListOf<ActionItem>()
        val jaActions = json.optJSONArray("actions")
        if (jaActions != null) {
            for (i in 0 until jaActions.length()) {
                val obj = jaActions.optJSONObject(i)
                if (obj != null) {
                    actions.add(ActionItem(
                        text = obj.optString("text", ""),
                        done = obj.optBoolean("done", false),
                        urgency = obj.optString("urgency", "medium"),
                    ))
                }
            }
        }
        val repetitions = mutableListOf<String>()
        val jaRep = json.optJSONArray("repetitions")
        if (jaRep != null) for (i in 0 until jaRep.length()) repetitions.add(jaRep.optString(i, ""))
        val data = DailyDigestData(
            date = json.optString("date", date),
            summary_text = json.optString("summary_text", ""),
            key_themes = keyThemes,
            emotions = emotions,
            actions = actions,
            total_recordings = json.optInt("total_recordings", 0),
            total_duration = json.optString("total_duration", "0m 0s"),
            repetitions = repetitions,
        )
        DailyDigestResult.Success(data)
    } catch (e: Exception) {
        DailyDigestResult.Error(e.message ?: e.javaClass.simpleName)
    }
}
