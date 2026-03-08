package com.reflexio.app.ui.screens

import androidx.compose.foundation.background
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
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
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
import androidx.compose.material3.SuggestionChip
import androidx.compose.material3.SuggestionChipDefaults
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
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
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
private val ColorGreen = Color(0xFF4CAF50)
private val ColorOrange = Color(0xFFFF9800)
private val ColorRose = Color(0xFFE91E63)
private val ColorBlue = Color(0xFF2196F3)

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
                // ПОЧЕМУ notice banner: сервер может вернуть предыдущий день
                // с объяснением "дайджест будет готов к 18:30".
                data!!.notice?.let { noticeText ->
                    Card(
                        modifier = Modifier.fillMaxWidth(),
                        colors = CardDefaults.cardColors(
                            containerColor = ColorAmber.copy(alpha = 0.15f),
                        ),
                    ) {
                        Text(
                            text = noticeText,
                            style = MaterialTheme.typography.bodySmall,
                            color = ColorAmber,
                            modifier = Modifier.padding(12.dp),
                        )
                    }
                    Spacer(modifier = Modifier.height(8.dp))
                }
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
        val sourcesCount = data.sources_count
        val totalRecordings = data.total_recordings

        // === Пустое состояние: записей нет (согласовано с бэкендом _status=empty, _notice) ===
        if (totalRecordings == 0 || sourcesCount == 0) {
            Card(
                modifier = Modifier.fillMaxWidth(),
                colors = CardDefaults.cardColors(
                    containerColor = ColorTeal.copy(alpha = 0.08f),
                ),
                shape = RoundedCornerShape(12.dp),
            ) {
                Column(modifier = Modifier.padding(16.dp)) {
                    Text(
                        text = data.notice.takeIf { data.status == "empty" } ?: "Сегодня записей пока нет.",
                        style = MaterialTheme.typography.bodyLarge,
                        color = MaterialTheme.colorScheme.onSurface,
                    )
                    Spacer(modifier = Modifier.height(8.dp))
                    Text(
                        text = "Нажмите «Запись» внизу экрана, чтобы начать.",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            }
            Spacer(modifier = Modifier.height(16.dp))
        }

        // === Confidence UX: data quality label ===
        if (sourcesCount in 1..4) {
            Text(
                text = "На основе $sourcesCount записей — мало данных",
                style = MaterialTheme.typography.labelSmall,
                color = ColorAmber,
                modifier = Modifier.padding(bottom = 8.dp),
            )
        } else if (sourcesCount >= 5) {
            Text(
                text = "На основе $sourcesCount записей",
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.outline,
                modifier = Modifier.padding(bottom = 8.dp),
            )
        }

        // === Verdict Card (WOW) ===
        data.verdict?.let { verdict ->
            VerdictCard(verdict)
            Spacer(modifier = Modifier.height(20.dp))
        }

        // === Day Map (WOW) ===
        if (data.day_map.isNotEmpty()) {
            DayMapSection(data.day_map)
            Spacer(modifier = Modifier.height(20.dp))
        }

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

        // === Novelty & Repetitions (WOW chips) ===
        if (data.novelty.isNotEmpty() || data.repetitions.isNotEmpty()) {
            NoveltyRepetitionChips(novelty = data.novelty, repetitions = data.repetitions)
            Spacer(modifier = Modifier.height(20.dp))
        }

        // === Micro Step (WOW) ===
        data.micro_step?.let { step ->
            MicroStepCard(step)
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

// === WOW Composables ===

/**
 * Вердикт дня: яркое предложение + 2 evidence-цитаты из транскрипций.
 * ПОЧЕМУ evidence: вердикт без цитат — "trust me bro". С цитатами — обоснованный вывод.
 */
@Composable
private fun VerdictCard(verdict: VerdictData) {
    Card(
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(
            containerColor = ColorIndigo.copy(alpha = 0.1f),
        ),
        shape = RoundedCornerShape(16.dp),
    ) {
        Column(modifier = Modifier.padding(16.dp)) {
            Text(
                text = verdict.text,
                style = MaterialTheme.typography.titleMedium,
                fontWeight = FontWeight.Bold,
                lineHeight = 24.sp,
            )
            if (verdict.evidence_quotes.isNotEmpty()) {
                Spacer(modifier = Modifier.height(10.dp))
                verdict.evidence_quotes.forEach { quote ->
                    Row(
                        modifier = Modifier.padding(vertical = 2.dp),
                        verticalAlignment = Alignment.Top,
                    ) {
                        Box(
                            modifier = Modifier
                                .padding(top = 6.dp, end = 8.dp)
                                .size(4.dp)
                                .clip(CircleShape)
                                .background(ColorIndigo.copy(alpha = 0.5f)),
                        )
                        Text(
                            text = "\"$quote\"",
                            style = MaterialTheme.typography.bodySmall,
                            fontStyle = FontStyle.Italic,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                            maxLines = 2,
                            overflow = TextOverflow.Ellipsis,
                        )
                    }
                }
            }
        }
    }
}

/**
 * Карта дня: 3 карточки peak/valley/fork с иконками и временем.
 * ПОЧЕМУ горизонтальный scroll: 3 карточки не помещаются по ширине на маленьких экранах.
 */
@Composable
private fun DayMapSection(points: List<DayMapPoint>) {
    SectionHeader("Карта дня")
    LazyRow(
        horizontalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        items(points) { point ->
            val (icon, color) = when (point.type) {
                "peak" -> "^" to ColorGreen
                "valley" -> "v" to ColorRose
                "fork" -> "<>" to ColorBlue
                else -> "·" to ColorAmber
            }
            Card(
                modifier = Modifier.width(160.dp),
                colors = CardDefaults.cardColors(
                    containerColor = color.copy(alpha = 0.1f),
                ),
                shape = RoundedCornerShape(12.dp),
            ) {
                Column(modifier = Modifier.padding(12.dp)) {
                    Row(
                        verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.spacedBy(6.dp),
                    ) {
                        Box(
                            modifier = Modifier
                                .size(24.dp)
                                .clip(CircleShape)
                                .background(color.copy(alpha = 0.2f)),
                            contentAlignment = Alignment.Center,
                        ) {
                            Text(
                                text = icon,
                                style = MaterialTheme.typography.labelSmall,
                                fontWeight = FontWeight.Bold,
                                color = color,
                            )
                        }
                        Text(
                            text = point.time,
                            style = MaterialTheme.typography.labelMedium,
                            fontWeight = FontWeight.SemiBold,
                            color = color,
                        )
                    }
                    Spacer(modifier = Modifier.height(6.dp))
                    Text(
                        text = point.description,
                        style = MaterialTheme.typography.bodySmall,
                        maxLines = 3,
                        overflow = TextOverflow.Ellipsis,
                    )
                    Spacer(modifier = Modifier.height(4.dp))
                    Text(
                        text = point.emotion,
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.outline,
                    )
                }
            }
        }
    }
}

/**
 * Чипы новизны (зелёные) и повторов (оранжевые).
 */
@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun NoveltyRepetitionChips(novelty: List<String>, repetitions: List<RepetitionData>) {
    SectionHeader("Темы: новое и повторы")
    FlowRow(
        horizontalArrangement = Arrangement.spacedBy(8.dp),
        verticalArrangement = Arrangement.spacedBy(4.dp),
    ) {
        novelty.forEach { topic ->
            SuggestionChip(
                onClick = {},
                label = { Text("+ $topic", style = MaterialTheme.typography.labelMedium) },
                colors = SuggestionChipDefaults.suggestionChipColors(
                    containerColor = ColorGreen.copy(alpha = 0.15f),
                    labelColor = ColorGreen,
                ),
            )
        }
        repetitions.forEach { rep ->
            SuggestionChip(
                onClick = {},
                label = {
                    Text(
                        "${rep.topic} (${rep.streak_days}д)",
                        style = MaterialTheme.typography.labelMedium,
                    )
                },
                colors = SuggestionChipDefaults.suggestionChipColors(
                    containerColor = ColorOrange.copy(alpha = 0.15f),
                    labelColor = ColorOrange,
                ),
            )
        }
    }
}

/**
 * Карточка микро-шага на завтра с domain badge.
 */
@Composable
private fun MicroStepCard(step: MicroStepData) {
    SectionHeader("Микро-шаг на завтра")
    Card(
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(
            containerColor = ColorTeal.copy(alpha = 0.1f),
        ),
        shape = RoundedCornerShape(12.dp),
    ) {
        Column(modifier = Modifier.padding(14.dp)) {
            Row(
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                Text(
                    text = step.action,
                    style = MaterialTheme.typography.bodyMedium,
                    fontWeight = FontWeight.SemiBold,
                    modifier = Modifier.weight(1f),
                )
                // Domain badge
                Box(
                    modifier = Modifier
                        .clip(RoundedCornerShape(6.dp))
                        .background(ColorTeal.copy(alpha = 0.2f))
                        .padding(horizontal = 8.dp, vertical = 2.dp),
                ) {
                    Text(
                        text = step.domain,
                        style = MaterialTheme.typography.labelSmall,
                        color = ColorTeal,
                        fontWeight = FontWeight.Medium,
                    )
                }
            }
            if (step.why.isNotBlank()) {
                Spacer(modifier = Modifier.height(4.dp))
                Text(
                    text = step.why,
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        }
    }
}

// === Data classes ===

private data class VerdictData(
    val text: String,
    val evidence_quotes: List<String>,
)

private data class DayMapPoint(
    val type: String,  // "peak" | "valley" | "fork"
    val time: String,
    val description: String,
    val emotion: String,
)

private data class MicroStepData(
    val action: String,
    val why: String,
    val domain: String,
)

private data class RepetitionData(
    val topic: String,
    val streak_days: Int,
)

private data class DailyDigestData(
    val date: String,
    val summary_text: String,
    val key_themes: List<String>,
    val emotions: List<String>,
    val actions: List<ActionItem>,
    val total_recordings: Int,
    val total_duration: String,
    val repetitions: List<RepetitionData>,
    val sources_count: Int = 0,
    // WOW fields (nullable — backward compatible)
    val verdict: VerdictData? = null,
    val day_map: List<DayMapPoint> = emptyList(),
    val micro_step: MicroStepData? = null,
    val novelty: List<String> = emptyList(),
    // ПОЧЕМУ _notice/_status: сервер pre-compute дайджест в 18:00.
    // До 18:30 возвращает предыдущий день + notice объяснение.
    val notice: String? = null,
    val status: String? = null,  // "ready" | "pending" | "generating"
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
    // ПОЧЕМУ 30s: с pre-compute кешем ответ мгновенный.
    // 30s — достаточно для inline fallback на прошлые дни.
    val client = OkHttpClient.Builder()
        .connectTimeout(15, TimeUnit.SECONDS)
        .readTimeout(30, TimeUnit.SECONDS)
        .build()
    return try {
        val requestBuilder = Request.Builder().url(url).get()
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
        // Repetitions — now structured objects {topic, streak_days}
        val repetitions = mutableListOf<RepetitionData>()
        val jaRep = json.optJSONArray("repetitions")
        if (jaRep != null) {
            for (i in 0 until jaRep.length()) {
                val repObj = jaRep.optJSONObject(i)
                if (repObj != null) {
                    repetitions.add(RepetitionData(
                        topic = repObj.optString("topic", ""),
                        streak_days = repObj.optInt("streak_days", 0),
                    ))
                } else {
                    // backward compat: old string format
                    val repStr = jaRep.optString(i, "")
                    if (repStr.isNotBlank()) {
                        repetitions.add(RepetitionData(topic = repStr, streak_days = 0))
                    }
                }
            }
        }

        // WOW: verdict
        val verdict = json.optJSONObject("verdict")?.let { v ->
            val quotes = mutableListOf<String>()
            val jaQuotes = v.optJSONArray("evidence_quotes")
            if (jaQuotes != null) for (i in 0 until jaQuotes.length()) quotes.add(jaQuotes.optString(i, ""))
            VerdictData(
                text = v.optString("text", ""),
                evidence_quotes = quotes,
            )
        }

        // WOW: day_map
        val dayMap = mutableListOf<DayMapPoint>()
        val jaDayMap = json.optJSONArray("day_map")
        if (jaDayMap != null) {
            for (i in 0 until jaDayMap.length()) {
                val p = jaDayMap.optJSONObject(i) ?: continue
                dayMap.add(DayMapPoint(
                    type = p.optString("type", "peak"),
                    time = p.optString("time", ""),
                    description = p.optString("description", ""),
                    emotion = p.optString("emotion", ""),
                ))
            }
        }

        // WOW: micro_step
        val microStep = json.optJSONObject("micro_step")?.let { ms ->
            MicroStepData(
                action = ms.optString("action", ""),
                why = ms.optString("why", ""),
                domain = ms.optString("domain", "growth"),
            )
        }

        // WOW: novelty
        val novelty = mutableListOf<String>()
        val jaNovelty = json.optJSONArray("novelty")
        if (jaNovelty != null) for (i in 0 until jaNovelty.length()) novelty.add(jaNovelty.optString(i, ""))

        val data = DailyDigestData(
            date = json.optString("date", date),
            summary_text = json.optString("summary_text", ""),
            key_themes = keyThemes,
            emotions = emotions,
            actions = actions,
            total_recordings = json.optInt("total_recordings", 0),
            total_duration = json.optString("total_duration", "0m 0s"),
            repetitions = repetitions,
            sources_count = json.optInt("sources_count", 0),
            verdict = verdict,
            day_map = dayMap,
            micro_step = microStep,
            novelty = novelty,
            notice = if (json.has("_notice")) json.getString("_notice") else null,
            status = if (json.has("_status")) json.getString("_status") else null,
        )
        DailyDigestResult.Success(data)
    } catch (e: Exception) {
        DailyDigestResult.Error(e.message ?: e.javaClass.simpleName)
    }
}
