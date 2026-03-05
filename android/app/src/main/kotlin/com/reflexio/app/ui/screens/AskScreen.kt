package com.reflexio.app.ui.screens

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.animation.expandVertically
import androidx.compose.animation.shrinkVertically
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
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ExpandLess
import androidx.compose.material.icons.filled.ExpandMore
import androidx.compose.material.icons.filled.Search
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.SuggestionChip
import androidx.compose.material3.SuggestionChipDefaults
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import com.reflexio.app.BuildConfig
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONArray
import org.json.JSONObject
import java.util.concurrent.TimeUnit

// ──────────────────────────────────────────────
// Palette: confidence levels
// ──────────────────────────────────────────────

private val ColorHigh = Color(0xFF4CAF50)      // green
private val ColorMedium = Color(0xFF2196F3)    // blue
private val ColorLow = Color(0xFFFF9800)       // amber
private val ColorSpeculative = Color(0xFFF44336) // red

private fun confidenceColor(label: String): Color = when (label) {
    "high" -> ColorHigh
    "medium" -> ColorMedium
    "low" -> ColorLow
    else -> ColorSpeculative
}

private fun confidenceLabel(label: String): String = when (label) {
    "high" -> "Высокая уверенность"
    "medium" -> "Средняя уверенность"
    "low" -> "Низкая уверенность"
    else -> "Предположение"
}

/** Человечный текст для confidence вместо процентов. */
private fun confidenceHumanLabel(label: String): String = when (label) {
    "high" -> "высокая"
    "medium" -> "средняя"
    "low" -> "низкая"
    else -> "предположительная"
}

// ──────────────────────────────────────────────
// Data classes
// ──────────────────────────────────────────────

private data class EvidenceMeta(
    val id: String,
    val timestamp: String,
    val sentimentScore: Double,
    val topTopic: String,
)

// Rich data from digest
private data class AskDayMapPoint(
    val label: String,   // "peak" / "valley" / "fork"
    val time: String,
    val text: String,
)

private data class MicroStepInfo(
    val action: String,
    val why: String,
    val domain: String,
)

private data class DigestRichData(
    val verdictText: String?,
    val verdictQuotes: List<String>,
    val dayMap: List<AskDayMapPoint>,
    val keyThemes: List<String>,
    val emotions: List<String>,
    val microStep: MicroStepInfo?,
    val novelty: List<String>,
    val summaryText: String?,
)

// Rich data from events
private data class EventsRichData(
    val total: Int,
    val topTopics: List<String>,
)

private data class AskResult(
    val answer: String,
    val confidence: Double,
    val confidenceLabel: String,
    val evidenceCount: Int,
    val toolsUsed: List<String>,
    val totalMs: Double,
    val needsClarification: Boolean,
    val warning: String?,
    val uiHint: String,
    val evidenceMetadata: List<EvidenceMeta>,
    val primaryTool: String?,
    val digestData: DigestRichData?,
    val eventsData: EventsRichData?,
)

private sealed class AskState {
    object Idle : AskState()
    object Loading : AskState()
    data class Success(val result: AskResult) : AskState()
    data class Error(val message: String) : AskState()
}

// ──────────────────────────────────────────────
// JSON Parsing helpers
// ──────────────────────────────────────────────

private fun parseDigestData(dataObj: JSONObject): DigestRichData {
    val verdict = dataObj.optJSONObject("verdict")
    val verdictText = verdict?.optString("text", "")?.takeIf { it.isNotBlank() }
    val verdictQuotes = mutableListOf<String>()
    verdict?.optJSONArray("evidence_quotes")?.let { arr ->
        for (i in 0 until arr.length()) verdictQuotes.add(arr.getString(i))
    }

    val dayMap = mutableListOf<AskDayMapPoint>()
    dataObj.optJSONArray("day_map")?.let { arr ->
        for (i in 0 until arr.length()) {
            val p = arr.getJSONObject(i)
            dayMap.add(AskDayMapPoint(
                label = p.optString("label", ""),
                time = p.optString("time", ""),
                text = p.optString("text", ""),
            ))
        }
    }

    val keyThemes = mutableListOf<String>()
    dataObj.optJSONArray("key_themes")?.let { arr ->
        for (i in 0 until arr.length()) keyThemes.add(arr.getString(i))
    }

    val emotions = mutableListOf<String>()
    dataObj.optJSONArray("emotions")?.let { arr ->
        for (i in 0 until arr.length()) {
            val item = arr.opt(i)
            if (item is String) {
                emotions.add(item)
            } else if (item is JSONObject) {
                item.optString("emotion", "").takeIf { it.isNotBlank() }?.let { emotions.add(it) }
            }
        }
    }

    val microStep = dataObj.optJSONObject("micro_step")?.let { ms ->
        val action = ms.optString("action", "")
        if (action.isNotBlank()) MicroStepInfo(
            action = action,
            why = ms.optString("why", ""),
            domain = ms.optString("domain", "growth"),
        ) else null
    }

    val novelty = mutableListOf<String>()
    dataObj.optJSONArray("novelty")?.let { arr ->
        for (i in 0 until arr.length()) novelty.add(arr.getString(i))
    }

    return DigestRichData(
        verdictText = verdictText,
        verdictQuotes = verdictQuotes,
        dayMap = dayMap,
        keyThemes = keyThemes,
        emotions = emotions,
        microStep = microStep,
        novelty = novelty,
        summaryText = dataObj.optString("summary_text", "").takeIf { it.isNotBlank() },
    )
}

private fun parseEventsData(dataObj: JSONObject): EventsRichData {
    val total = dataObj.optInt("total", 0)
    val topTopics = mutableListOf<String>()
    // Собираем top topics из events[].topics_json
    dataObj.optJSONArray("events")?.let { arr ->
        val counter = mutableMapOf<String, Int>()
        for (i in 0 until arr.length()) {
            val ev = arr.getJSONObject(i)
            val topicsRaw = ev.optString("topics_json", "")
            if (topicsRaw.isNotBlank() && topicsRaw.startsWith("[")) {
                try {
                    val topics = JSONArray(topicsRaw)
                    for (j in 0 until topics.length()) {
                        val t = topics.getString(j).trim()
                        if (t.isNotBlank()) counter[t] = (counter[t] ?: 0) + 1
                    }
                } catch (_: Exception) {}
            }
        }
        counter.entries.sortedByDescending { it.value }.take(5).forEach { topTopics.add(it.key) }
    }
    return EventsRichData(total = total, topTopics = topTopics)
}

// ──────────────────────────────────────────────
// HTTP
// ──────────────────────────────────────────────

private val httpClient = OkHttpClient.Builder()
    .connectTimeout(10, TimeUnit.SECONDS)
    .readTimeout(30, TimeUnit.SECONDS)
    .build()

private fun postAsk(baseHttpUrl: String, question: String): AskResult {
    val body = JSONObject().apply {
        put("question", question)
        put("include_evidence", false)
    }.toString().toRequestBody("application/json".toMediaType())

    val requestBuilder = Request.Builder()
        .url("$baseHttpUrl/ask")
        .post(body)
    val apiKey = BuildConfig.SERVER_API_KEY
    if (apiKey.isNotBlank()) requestBuilder.addHeader("Authorization", "Bearer $apiKey")
    val request = requestBuilder.build()

    httpClient.newCall(request).execute().use { resp ->
        val raw = resp.body?.string() ?: throw RuntimeException("Empty response")
        if (!resp.isSuccessful) throw RuntimeException("HTTP ${resp.code}: $raw")
        val json = JSONObject(raw)

        val toolsArray = json.optJSONArray("tools_used")
        val tools = mutableListOf<String>()
        if (toolsArray != null) {
            for (i in 0 until toolsArray.length()) tools.add(toolsArray.getString(i))
        }

        val primaryTool = json.optString("primary_tool", "").takeIf { it.isNotBlank() }

        // Парсим evidence_metadata и ui_hint из data[0]
        var uiHint = "timeline"
        val evidenceMetadata = mutableListOf<EvidenceMeta>()
        var digestData: DigestRichData? = null
        var eventsData: EventsRichData? = null

        val dataArr = json.optJSONArray("data")
        if (dataArr != null && dataArr.length() > 0) {
            val first = dataArr.getJSONObject(0)
            uiHint = first.optString("ui_hint", "timeline")
            val evArr: JSONArray? = first.optJSONArray("evidence_metadata")
            if (evArr != null) {
                for (i in 0 until evArr.length()) {
                    val ev = evArr.getJSONObject(i)
                    evidenceMetadata.add(
                        EvidenceMeta(
                            id = ev.optString("id"),
                            timestamp = ev.optString("timestamp"),
                            sentimentScore = ev.optDouble("sentiment_score", 0.0),
                            topTopic = ev.optString("top_topic"),
                        )
                    )
                }
            }

            // Parse rich data based on primary_tool
            val innerData = first.optJSONObject("data")
            if (innerData != null) {
                when (primaryTool) {
                    "get_digest" -> digestData = try { parseDigestData(innerData) } catch (_: Exception) { null }
                    "query_events" -> eventsData = try { parseEventsData(innerData) } catch (_: Exception) { null }
                }
            }
        }

        return AskResult(
            answer = json.optString("answer", "Нет ответа"),
            confidence = json.optDouble("confidence", 0.0),
            confidenceLabel = json.optString("confidence_label", "speculative"),
            evidenceCount = json.optInt("evidence_count", 0),
            toolsUsed = tools,
            totalMs = json.optDouble("total_ms", 0.0),
            needsClarification = json.optBoolean("needs_clarification", false),
            warning = json.optString("warning", "").takeIf { it.isNotBlank() },
            uiHint = uiHint,
            evidenceMetadata = evidenceMetadata,
            primaryTool = primaryTool,
            digestData = digestData,
            eventsData = eventsData,
        )
    }
}

// ──────────────────────────────────────────────
// Composables
// ──────────────────────────────────────────────

/**
 * AskScreen — One Interface.
 *
 * ПОЧЕМУ одна точка входа:
 *   Пользователь не должен знать какой endpoint нужен для его вопроса.
 *   POST /ask -> orchestrator сам выберет тул(ы) и вернёт синтезированный ответ.
 *
 * Порядок рендера (meaning-first):
 *   1. Warning (если есть)
 *   2. Answer Card — verdict/summary (крупный текст)
 *   3. DayMap — 3 карточки peak/valley/fork
 *   4. Themes + Emotions — FlowRow чипов
 *   5. MicroStep — карточка рекомендации
 *   6. ConfidenceLine — "Ответ основан на N событиях, уверенность высокая"
 *   7. EvidenceTraceRow — timeline dots
 *   8. Детали — collapsed
 */
@Composable
fun AskScreen(
    baseHttpUrl: String,
    modifier: Modifier = Modifier,
) {
    var question by remember { mutableStateOf("") }
    var state by remember { mutableStateOf<AskState>(AskState.Idle) }
    var showDetails by remember { mutableStateOf(false) }
    val scope = rememberCoroutineScope()

    fun submit() {
        val q = question.trim()
        if (q.isBlank()) return
        state = AskState.Loading
        showDetails = false
        scope.launch {
            state = try {
                val result = withContext(Dispatchers.IO) { postAsk(baseHttpUrl, q) }
                AskState.Success(result)
            } catch (e: Exception) {
                AskState.Error(e.message ?: "Ошибка соединения")
            }
        }
    }

    Column(
        modifier = modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(horizontal = 16.dp, vertical = 8.dp),
    ) {
        // ── Input ──────────────────────────────
        OutlinedTextField(
            value = question,
            onValueChange = { question = it },
            placeholder = { Text("Спроси что угодно о своём дне...") },
            modifier = Modifier.fillMaxWidth(),
            minLines = 2,
            maxLines = 4,
            keyboardOptions = KeyboardOptions(imeAction = ImeAction.Send),
            keyboardActions = KeyboardActions(onSend = { submit() }),
        )
        Spacer(modifier = Modifier.height(8.dp))
        Button(
            onClick = { submit() },
            modifier = Modifier.align(Alignment.End),
            enabled = question.isNotBlank() && state !is AskState.Loading,
        ) {
            Icon(Icons.Default.Search, contentDescription = null, modifier = Modifier.size(18.dp))
            Spacer(modifier = Modifier.width(6.dp))
            Text("Спросить")
        }

        Spacer(modifier = Modifier.height(16.dp))

        // ── Result ─────────────────────────────
        when (val s = state) {
            is AskState.Idle -> {
                Text(
                    text = "Задай вопрос на естественном языке — система сама найдёт нужные данные.",
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    fontStyle = FontStyle.Italic,
                )
            }

            is AskState.Loading -> {
                Box(
                    modifier = Modifier.fillMaxWidth().padding(32.dp),
                    contentAlignment = Alignment.Center,
                ) {
                    CircularProgressIndicator()
                }
            }

            is AskState.Error -> {
                Card(
                    modifier = Modifier.fillMaxWidth(),
                    colors = CardDefaults.cardColors(
                        containerColor = ColorSpeculative.copy(alpha = 0.12f),
                    ),
                ) {
                    Text(
                        text = "Ошибка: ${s.message}",
                        style = MaterialTheme.typography.bodyMedium,
                        color = ColorSpeculative,
                        modifier = Modifier.padding(12.dp),
                    )
                }
            }

            is AskState.Success -> {
                val r = s.result

                // 1. Warning banner
                r.warning?.let { warn ->
                    Card(
                        modifier = Modifier.fillMaxWidth(),
                        colors = CardDefaults.cardColors(
                            containerColor = ColorLow.copy(alpha = 0.12f),
                        ),
                    ) {
                        Text(
                            text = warn,
                            style = MaterialTheme.typography.bodySmall,
                            color = ColorLow,
                            modifier = Modifier.padding(12.dp),
                        )
                    }
                    Spacer(modifier = Modifier.height(8.dp))
                }

                // 2. Answer Card — verdict/summary (meaning-first)
                Card(
                    modifier = Modifier.fillMaxWidth(),
                    colors = CardDefaults.cardColors(
                        containerColor = MaterialTheme.colorScheme.surfaceVariant,
                    ),
                ) {
                    Text(
                        text = r.answer,
                        style = MaterialTheme.typography.bodyLarge,
                        modifier = Modifier.padding(16.dp),
                    )
                }

                Spacer(modifier = Modifier.height(8.dp))

                // 3. DayMap (only for digest)
                r.digestData?.let { digest ->
                    if (digest.dayMap.isNotEmpty()) {
                        AskDayMapSection(digest.dayMap)
                        Spacer(modifier = Modifier.height(8.dp))
                    }

                    // 4. Themes + Emotions
                    if (digest.keyThemes.isNotEmpty() || digest.emotions.isNotEmpty()) {
                        AskThemesSection(digest.keyThemes, digest.emotions)
                        Spacer(modifier = Modifier.height(8.dp))
                    }

                    // 5. MicroStep
                    digest.microStep?.let { step ->
                        AskMicroStepCard(step)
                        Spacer(modifier = Modifier.height(8.dp))
                    }
                }

                // For events: show top topics as chips
                r.eventsData?.let { events ->
                    if (events.topTopics.isNotEmpty()) {
                        AskThemesSection(events.topTopics, emptyList())
                        Spacer(modifier = Modifier.height(8.dp))
                    }
                }

                // 6. ConfidenceLine — human-readable text
                ConfidenceLine(
                    label = r.confidenceLabel,
                    evidenceCount = r.evidenceCount,
                )
                Spacer(modifier = Modifier.height(8.dp))

                // 7. EvidenceTrace — horizontal dots
                if (r.evidenceMetadata.isNotEmpty()) {
                    EvidenceTraceRow(r.evidenceMetadata)
                    Spacer(modifier = Modifier.height(8.dp))
                }

                // 8. Expandable details
                TextButton(
                    onClick = { showDetails = !showDetails },
                    modifier = Modifier.align(Alignment.End),
                ) {
                    Text("Детали")
                    Spacer(modifier = Modifier.width(4.dp))
                    Icon(
                        if (showDetails) Icons.Default.ExpandLess else Icons.Default.ExpandMore,
                        contentDescription = null,
                        modifier = Modifier.size(18.dp),
                    )
                }

                AnimatedVisibility(
                    visible = showDetails,
                    enter = expandVertically(),
                    exit = shrinkVertically(),
                ) {
                    Card(
                        modifier = Modifier.fillMaxWidth(),
                        colors = CardDefaults.cardColors(
                            containerColor = MaterialTheme.colorScheme.surface,
                        ),
                    ) {
                        Column(modifier = Modifier.padding(12.dp)) {
                            DetailRow("Улик найдено", "${r.evidenceCount}")
                            DetailRow("Время ответа", "${r.totalMs.toInt()} мс")
                            DetailRow("Тулы", r.toolsUsed.joinToString(", ").ifEmpty { "-" })
                            if (r.needsClarification) {
                                Spacer(modifier = Modifier.height(4.dp))
                                Text(
                                    text = "Уточните вопрос для более точного ответа",
                                    style = MaterialTheme.typography.bodySmall,
                                    color = ColorLow,
                                )
                            }
                        }
                    }
                }
            }
        }
    }
}

// ──────────────────────────────────────────────
// New composables: meaning-first sections
// ──────────────────────────────────────────────

/**
 * ConfidenceLine — человечный текст вместо процентов.
 * "Ответ основан на 6 событиях, уверенность высокая"
 */
@Composable
private fun ConfidenceLine(label: String, evidenceCount: Int) {
    val color = confidenceColor(label)
    val evText = when {
        evidenceCount == 0 -> "без источников"
        evidenceCount == 1 -> "на 1 событии"
        evidenceCount in 2..4 -> "на $evidenceCount событиях"
        else -> "на $evidenceCount событиях"
    }
    Text(
        text = "Ответ основан $evText, уверенность ${confidenceHumanLabel(label)}",
        style = MaterialTheme.typography.bodySmall,
        color = color,
    )
}

/**
 * AskDayMapSection — горизонтальный скролл 3 ключевых моментов дня.
 * Аналог DailySummaryScreen day_map карточек.
 */
@Composable
private fun AskDayMapSection(points: List<AskDayMapPoint>) {
    val labelEmoji = mapOf("peak" to "+", "valley" to "-", "fork" to "?")

    LazyRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        items(points) { point: AskDayMapPoint ->
            Card(
                modifier = Modifier.width(200.dp),
                shape = RoundedCornerShape(12.dp),
                colors = CardDefaults.cardColors(
                    containerColor = MaterialTheme.colorScheme.surface,
                ),
            ) {
                Column(modifier = Modifier.padding(12.dp)) {
                    Row(
                        verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.spacedBy(4.dp),
                    ) {
                        Text(
                            text = labelEmoji[point.label] ?: "",
                            style = MaterialTheme.typography.titleMedium,
                        )
                        if (point.time.isNotBlank()) {
                            Text(
                                text = point.time,
                                style = MaterialTheme.typography.labelSmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                            )
                        }
                    }
                    if (point.text.isNotBlank()) {
                        Spacer(modifier = Modifier.height(4.dp))
                        Text(
                            text = point.text,
                            style = MaterialTheme.typography.bodySmall,
                            maxLines = 3,
                        )
                    }
                }
            }
        }
    }
}

/**
 * AskThemesSection — FlowRow чипов с темами и эмоциями.
 */
@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun AskThemesSection(themes: List<String>, emotions: List<String>) {
    FlowRow(
        horizontalArrangement = Arrangement.spacedBy(6.dp),
        verticalArrangement = Arrangement.spacedBy(4.dp),
    ) {
        themes.forEach { theme ->
            SuggestionChip(
                onClick = {},
                label = { Text(theme, style = MaterialTheme.typography.labelSmall) },
                colors = SuggestionChipDefaults.suggestionChipColors(
                    containerColor = ColorMedium.copy(alpha = 0.1f),
                    labelColor = ColorMedium,
                ),
            )
        }
        emotions.forEach { emotion ->
            SuggestionChip(
                onClick = {},
                label = { Text(emotion, style = MaterialTheme.typography.labelSmall) },
                colors = SuggestionChipDefaults.suggestionChipColors(
                    containerColor = ColorLow.copy(alpha = 0.1f),
                    labelColor = ColorLow,
                ),
            )
        }
    }
}

/**
 * AskMicroStepCard — карточка с рекомендацией на завтра.
 */
@Composable
private fun AskMicroStepCard(step: MicroStepInfo) {
    Card(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(12.dp),
        colors = CardDefaults.cardColors(
            containerColor = ColorHigh.copy(alpha = 0.08f),
        ),
    ) {
        Column(modifier = Modifier.padding(12.dp)) {
            Text(
                text = "Микрошаг на завтра",
                style = MaterialTheme.typography.labelMedium,
                fontWeight = FontWeight.Bold,
                color = ColorHigh,
            )
            Spacer(modifier = Modifier.height(4.dp))
            Text(
                text = step.action,
                style = MaterialTheme.typography.bodyMedium,
            )
            if (step.why.isNotBlank()) {
                Spacer(modifier = Modifier.height(2.dp))
                Text(
                    text = step.why,
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        }
    }
}

// ──────────────────────────────────────────────
// Existing composables (preserved)
// ──────────────────────────────────────────────

/**
 * ConfidenceBadge — chip с пульсирующей анимацией для speculative результатов.
 * Сохранён для backward compatibility (не используется в новом layout,
 * но может пригодиться в других экранах).
 */
@Composable
private fun ConfidenceBadge(label: String, confidence: Double) {
    val color = confidenceColor(label)
    val infiniteTransition = rememberInfiniteTransition(label = "confidence_pulse")
    val pulseAlpha by infiniteTransition.animateFloat(
        initialValue = 0.5f,
        targetValue = 1.0f,
        animationSpec = infiniteRepeatable(tween(800), RepeatMode.Reverse),
        label = "pulse",
    )
    val containerAlpha = if (label == "speculative") pulseAlpha else 1f

    SuggestionChip(
        onClick = {},
        label = {
            Text(
                text = "${confidenceLabel(label)} · ${(confidence * 100).toInt()}%",
                fontWeight = FontWeight.Medium,
            )
        },
        colors = SuggestionChipDefaults.suggestionChipColors(
            containerColor = color.copy(alpha = 0.15f * containerAlpha),
            labelColor = color,
        ),
    )
}

/**
 * EvidenceTraceRow — горизонтальная лента улик.
 * [14:32 · стресс · red] [15:10 · работа · amber] [16:45 · финансы · green]
 */
@Composable
private fun EvidenceTraceRow(evidenceList: List<EvidenceMeta>) {
    LazyRow(
        horizontalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        items(evidenceList) { ev -> EvidenceCard(ev) }
    }
}

@Composable
private fun EvidenceCard(ev: EvidenceMeta) {
    val dotColor = when {
        ev.sentimentScore >= 0.7 -> ColorHigh
        ev.sentimentScore >= 0.4 -> ColorLow
        else -> ColorSpeculative
    }
    val timeStr = ev.timestamp.let { ts ->
        val sep = ts.indexOfFirst { it == 'T' || it == ' ' }
        if (sep >= 0 && sep + 6 <= ts.length) ts.substring(sep + 1, sep + 6) else ts.take(5)
    }

    Card(
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
    ) {
        Row(
            modifier = Modifier.padding(horizontal = 10.dp, vertical = 6.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(5.dp),
        ) {
            Text(text = timeStr, style = MaterialTheme.typography.labelSmall)
            if (ev.topTopic.isNotBlank()) {
                Text(
                    text = "· ${ev.topTopic}",
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
            Box(modifier = Modifier.size(8.dp).background(dotColor, CircleShape))
        }
    }
}

@Composable
private fun DetailRow(label: String, value: String) {
    Row(
        modifier = Modifier.fillMaxWidth().padding(vertical = 2.dp),
        horizontalArrangement = Arrangement.SpaceBetween,
    ) {
        Text(
            text = label,
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        Text(
            text = value,
            style = MaterialTheme.typography.bodySmall,
            fontWeight = FontWeight.Medium,
        )
    }
}
