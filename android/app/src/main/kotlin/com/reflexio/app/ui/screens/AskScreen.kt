package com.reflexio.app.ui.screens

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.animation.expandVertically
import androidx.compose.animation.fadeIn
import androidx.compose.animation.shrinkVertically
import androidx.compose.animation.slideInHorizontally
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
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
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.draw.scale
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.PathEffect
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.text.font.FontStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import com.reflexio.app.BuildConfig
import com.reflexio.app.ui.components.ShimmerLine
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONArray
import org.json.JSONObject
import java.util.concurrent.TimeUnit

// ──────────────────────────────────────────────
// Palette
// ──────────────────────────────────────────────

private val ColorHigh = Color(0xFF4CAF50)
private val ColorMedium = Color(0xFF2196F3)
private val ColorLow = Color(0xFFFF9800)
private val ColorSpeculative = Color(0xFFF44336)

private val ColorTeal = Color(0xFF00E5CC)
private val ColorIndigo = Color(0xFF7C6CFF)
private val ColorAmber = Color(0xFFFFB74D)
private val ColorRose = Color(0xFFE91E63)
private val ColorBlue = Color(0xFF42A5F5)

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

private data class AskDayMapPoint(
    val label: String,   // "peak" / "valley" / "fork"
    val time: String,
    val text: String,
    val emotion: String = "",
)

private data class MicroStepInfo(
    val action: String,
    val why: String,
    val domain: String,
)

private data class AcousticProfile(
    val avgEnergy: Float,
    val arousal: Float,
    val hourlyEnergy: List<Float>,
)

private data class InsightItem(
    val role: String,
    val text: String,
    val confidence: Float,
)

private data class NoveltyInfo(
    val newTopics: List<String>,
    val score: Float,
)

private data class RepetitionItem(
    val topic: String,
    val count: Int,
    val streakDays: Int,
)

private data class RepetitionsInfo(
    val items: List<RepetitionItem>,
    val alertText: String?,
)

private data class EmotionInfo(
    val primary: String,
    val secondary: String?,
    val valence: String,
)

private data class BalanceInfo(
    val work: Float,
    val relationships: Float,
    val health: Float,
    val growth: Float,
)

private data class DigestRichData(
    val verdictText: String?,
    val verdictQuotes: List<String>,
    val emotionalArc: String?,
    val dayMap: List<AskDayMapPoint>,
    val keyThemes: List<String>,
    val emotions: List<String>,
    val microStep: MicroStepInfo?,
    val novelty: List<String>,
    val summaryText: String?,
    // New fields for Emotional Mirror
    val acousticProfile: AcousticProfile? = null,
    val insights: List<InsightItem> = emptyList(),
    val noveltyInfo: NoveltyInfo? = null,
    val repetitionsInfo: RepetitionsInfo? = null,
    val emotionInfo: EmotionInfo? = null,
    val balance: BalanceInfo? = null,
)

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
    // Also check "quotes" key
    verdict?.optJSONArray("quotes")?.let { arr ->
        if (verdictQuotes.isEmpty()) {
            for (i in 0 until arr.length()) verdictQuotes.add(arr.getString(i))
        }
    }
    val emotionalArc = verdict?.optString("emotional_arc", "")?.takeIf { it.isNotBlank() }

    val dayMap = mutableListOf<AskDayMapPoint>()
    dataObj.optJSONArray("day_map")?.let { arr ->
        for (i in 0 until arr.length()) {
            val p = arr.getJSONObject(i)
            dayMap.add(AskDayMapPoint(
                label = p.optString("type", p.optString("label", "")),
                time = p.optString("time", ""),
                text = p.optString("description", p.optString("text", "")),
                emotion = p.optString("emotion", ""),
            ))
        }
    }

    val keyThemes = mutableListOf<String>()
    dataObj.optJSONArray("key_themes")?.let { arr ->
        for (i in 0 until arr.length()) keyThemes.add(arr.getString(i))
    }

    val emotionsList = mutableListOf<String>()
    dataObj.optJSONArray("emotions")?.let { arr ->
        for (i in 0 until arr.length()) {
            val item = arr.opt(i)
            if (item is String) {
                emotionsList.add(item)
            } else if (item is JSONObject) {
                item.optString("emotion", "").takeIf { it.isNotBlank() }?.let { emotionsList.add(it) }
            }
        }
    }

    val microStep = dataObj.optJSONObject("micro_step")?.let { ms ->
        val action = ms.optString("action", ms.optString("text", ""))
        if (action.isNotBlank()) MicroStepInfo(
            action = action,
            why = ms.optString("why", ""),
            domain = ms.optString("category", ms.optString("domain", "growth")),
        ) else null
    }

    val noveltyList = mutableListOf<String>()
    val noveltyObj = dataObj.opt("novelty")
    var noveltyInfo: NoveltyInfo? = null
    if (noveltyObj is JSONObject) {
        val topics = mutableListOf<String>()
        noveltyObj.optJSONArray("new_topics")?.let { arr ->
            for (i in 0 until arr.length()) topics.add(arr.getString(i))
        }
        noveltyInfo = NoveltyInfo(
            newTopics = topics,
            score = noveltyObj.optDouble("score", 0.0).toFloat(),
        )
        noveltyList.addAll(topics)
    } else if (noveltyObj is JSONArray) {
        for (i in 0 until noveltyObj.length()) noveltyList.add(noveltyObj.getString(i))
        if (noveltyList.isNotEmpty()) {
            noveltyInfo = NoveltyInfo(newTopics = noveltyList, score = 0.5f)
        }
    }

    // Parse acoustic_profile
    val acousticProfile = dataObj.optJSONObject("acoustic_profile")?.let { ap ->
        val hourly = mutableListOf<Float>()
        ap.optJSONArray("hourly_energy")?.let { arr ->
            for (i in 0 until arr.length()) hourly.add(arr.optDouble(i, 0.0).toFloat())
        }
        AcousticProfile(
            avgEnergy = ap.optDouble("avg_energy", 0.0).toFloat(),
            arousal = ap.optDouble("arousal", 0.5).toFloat(),
            hourlyEnergy = hourly,
        )
    }

    // Parse insights
    val insights = mutableListOf<InsightItem>()
    dataObj.optJSONArray("insights")?.let { arr ->
        for (i in 0 until arr.length()) {
            val ins = arr.getJSONObject(i)
            insights.add(InsightItem(
                role = ins.optString("role", "analyst"),
                text = ins.optString("text", ""),
                confidence = ins.optDouble("confidence", 0.5).toFloat(),
            ))
        }
    }

    // Parse repetitions
    val repetitionsInfo = dataObj.opt("repetitions")?.let { rep ->
        if (rep is JSONObject) {
            val items = mutableListOf<RepetitionItem>()
            rep.optJSONArray("items")?.let { arr ->
                for (i in 0 until arr.length()) {
                    val ri = arr.getJSONObject(i)
                    items.add(RepetitionItem(
                        topic = ri.optString("topic", ""),
                        count = ri.optInt("count", 0),
                        streakDays = ri.optInt("streak_days", 0),
                    ))
                }
            }
            RepetitionsInfo(
                items = items,
                alertText = rep.optString("alert_text", "").takeIf { it.isNotBlank() },
            )
        } else null
    }

    // Parse emotions object (not array — structured form)
    val emotionsObj = dataObj.optJSONObject("emotions")
    val emotionInfo = emotionsObj?.let { eo ->
        EmotionInfo(
            primary = eo.optString("primary", ""),
            secondary = eo.optString("secondary", "").takeIf { it.isNotBlank() },
            valence = eo.optString("valence", "neutral"),
        )
    }

    // Parse balance
    val balance = dataObj.optJSONObject("balance")?.let { b ->
        BalanceInfo(
            work = b.optDouble("work", 0.0).toFloat(),
            relationships = b.optDouble("relationships", 0.0).toFloat(),
            health = b.optDouble("health", 0.0).toFloat(),
            growth = b.optDouble("growth", 0.0).toFloat(),
        )
    }

    return DigestRichData(
        verdictText = verdictText,
        verdictQuotes = verdictQuotes,
        emotionalArc = emotionalArc,
        dayMap = dayMap,
        keyThemes = keyThemes,
        emotions = emotionsList,
        microStep = microStep,
        novelty = noveltyList,
        summaryText = dataObj.optString("summary_text", "").takeIf { it.isNotBlank() },
        acousticProfile = acousticProfile,
        insights = insights,
        noveltyInfo = noveltyInfo,
        repetitionsInfo = repetitionsInfo,
        emotionInfo = emotionInfo,
        balance = balance,
    )
}

private fun parseEventsData(dataObj: JSONObject): EventsRichData {
    val total = dataObj.optInt("total", 0)
    val topTopics = mutableListOf<String>()
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
// Helpers
// ──────────────────────────────────────────────

private fun emotionEmoji(primary: String): String = when (primary.lowercase()) {
    "joy", "радость", "happiness" -> "\uD83D\uDE0A"
    "sadness", "грусть", "печаль" -> "\uD83D\uDE14"
    "anger", "злость", "гнев" -> "\uD83D\uDE20"
    "anxiety", "тревога", "fear", "страх" -> "\uD83D\uDE1F"
    "calm", "спокойствие", "peace" -> "\uD83E\uDDD8"
    "surprise", "удивление" -> "\uD83D\uDE2E"
    "love", "любовь" -> "\u2764\uFE0F"
    "excitement", "возбуждение", "энергия" -> "\u26A1"
    else -> "\uD83D\uDCAD"
}

private fun emotionColor(emotion: String): Color = when (emotion.lowercase()) {
    "joy", "радость", "happiness", "love", "любовь" -> ColorTeal
    "sadness", "грусть", "печаль" -> ColorBlue
    "anger", "злость", "гнев" -> ColorRose
    "anxiety", "тревога", "fear", "страх" -> ColorAmber
    "calm", "спокойствие", "peace" -> ColorIndigo
    else -> ColorIndigo
}

private fun valenceColor(valence: String): Color = when (valence.lowercase()) {
    "positive" -> ColorTeal
    "negative" -> ColorRose
    else -> ColorIndigo
}

private fun arousalLabel(arousal: Float): String = when {
    arousal < 0.35f -> "Спокойный день"
    arousal < 0.65f -> "Умеренный день"
    else -> "Энергичный день"
}

private fun insightRoleIcon(role: String): String = when (role.lowercase()) {
    "psychologist", "психолог" -> "\uD83E\uDDE0"
    "analyst", "аналитик" -> "\uD83D\uDCC8"
    "coach", "коуч" -> "\uD83C\uDFAF"
    "detective", "детектив" -> "\uD83D\uDD0D"
    "philosopher", "философ" -> "\uD83D\uDCA1"
    else -> "\uD83D\uDCDD"
}

private fun insightRoleLabel(role: String): String = when (role.lowercase()) {
    "psychologist", "психолог" -> "Психолог"
    "analyst", "аналитик" -> "Аналитик"
    "coach", "коуч" -> "Коуч"
    "detective", "детектив" -> "Детектив"
    "philosopher", "философ" -> "Философ"
    else -> role.replaceFirstChar { it.uppercase() }
}

// ──────────────────────────────────────────────
// Main Composable
// ──────────────────────────────────────────────

/**
 * AskScreen — Emotional Mirror.
 *
 * Порядок рендера (emotion-first):
 *   1. Warning (если есть)
 *   2. EmotionalPulseRing — hero element с arousal + emotion emoji
 *   3. VerdictHeroCard — verdict текст с gradient border + expandable quotes
 *   4. DayJourneyTimeline — вертикальная timeline с staggered animation
 *   5. EmotionRiver — horizontal pills
 *   6. InsightCarousel — 5 перспектив (swipe cards)
 *   7. PatternSignalRow — novelty + repetitions
 *   8. AskMicroStepCard — рекомендация с expandable why
 *   9. ConfidenceLine — human-readable
 *  10. EvidenceTraceRow + Details — collapsed
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
                AskShimmerSkeleton()
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

                // 1. Пустое состояние при 0 источников (смысл + действие); иначе — баннер предупреждения
                if (r.evidenceCount == 0) {
                    Card(
                        modifier = Modifier.fillMaxWidth(),
                        colors = CardDefaults.cardColors(
                            containerColor = ColorIndigo.copy(alpha = 0.08f),
                        ),
                        shape = RoundedCornerShape(12.dp),
                    ) {
                        Column(modifier = Modifier.padding(16.dp)) {
                            Text(
                                text = if (r.answer.contains("не найдено") || r.answer.contains("нет данных"))
                                    "По этому запросу данных пока нет."
                                else
                                    "Сегодня ещё нет записей.",
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
                    Spacer(modifier = Modifier.height(12.dp))
                } else {
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
                }

                // 2. EmotionalPulseRing (only for digest with acoustic data)
                r.digestData?.let { digest ->
                    if (digest.acousticProfile != null || digest.emotionInfo != null) {
                        EmotionalPulseRing(
                            emotionInfo = digest.emotionInfo,
                            arousal = digest.acousticProfile?.arousal ?: 0.5f,
                        )
                        Spacer(modifier = Modifier.height(16.dp))
                    }
                }

                // 3. VerdictHeroCard
                r.digestData?.let { digest ->
                    if (digest.verdictText != null) {
                        VerdictHeroCard(
                            verdictText = digest.verdictText,
                            quotes = digest.verdictQuotes,
                            emotionalArc = digest.emotionalArc,
                        )
                        Spacer(modifier = Modifier.height(12.dp))
                    }
                }
                // Fallback: show answer if no verdict
                if (r.digestData?.verdictText == null) {
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
                }

                r.digestData?.let { digest ->
                    // 4. DayJourneyTimeline (vertical)
                    if (digest.dayMap.isNotEmpty()) {
                        DayJourneyTimeline(digest.dayMap)
                        Spacer(modifier = Modifier.height(12.dp))
                    }

                    // 5. EmotionRiver
                    if (digest.emotionInfo != null || digest.emotions.isNotEmpty()) {
                        EmotionRiver(
                            emotionInfo = digest.emotionInfo,
                            emotionsList = digest.emotions,
                        )
                        Spacer(modifier = Modifier.height(12.dp))
                    }

                    // 6. InsightCarousel
                    if (digest.insights.isNotEmpty()) {
                        InsightCarousel(digest.insights)
                        Spacer(modifier = Modifier.height(12.dp))
                    }

                    // 7. PatternSignalRow
                    val hasNovelty = digest.noveltyInfo != null && digest.noveltyInfo.newTopics.isNotEmpty()
                    val hasRepetitions = digest.repetitionsInfo != null && digest.repetitionsInfo.items.any { it.streakDays > 2 }
                    if (hasNovelty || hasRepetitions) {
                        PatternSignalRow(
                            novelty = digest.noveltyInfo,
                            repetitions = digest.repetitionsInfo,
                        )
                        Spacer(modifier = Modifier.height(12.dp))
                    }

                    // 8. MicroStep
                    digest.microStep?.let { step ->
                        AskMicroStepCard(step)
                        Spacer(modifier = Modifier.height(8.dp))
                    }

                    // Themes (if no emotion river showed them)
                    if (digest.emotionInfo == null && digest.keyThemes.isNotEmpty()) {
                        AskThemesSection(digest.keyThemes, digest.emotions)
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

                // 9. ConfidenceLine
                ConfidenceLine(
                    label = r.confidenceLabel,
                    evidenceCount = r.evidenceCount,
                )
                Spacer(modifier = Modifier.height(8.dp))

                // 10. EvidenceTrace
                if (r.evidenceMetadata.isNotEmpty()) {
                    EvidenceTraceRow(r.evidenceMetadata)
                    Spacer(modifier = Modifier.height(8.dp))
                }

                // 11. Expandable details
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
                            DetailRow("Событий в ответе", "${r.evidenceCount}")
                            DetailRow("Время ответа", "${r.totalMs.toInt()} мс")
                            DetailRow("Инструменты", r.toolsUsed.joinToString(", ").ifEmpty { "-" })
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
// New composables: Emotional Mirror sections
// ──────────────────────────────────────────────

/**
 * AskShimmerSkeleton — shimmer loading вместо spinner.
 * Показывает форму будущего контента для снижения perceived wait time.
 */
@Composable
private fun AskShimmerSkeleton() {
    Column(
        modifier = Modifier.fillMaxWidth().padding(vertical = 8.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        // Pulse ring placeholder
        Box(modifier = Modifier.align(Alignment.CenterHorizontally)) {
            ShimmerLine(modifier = Modifier.size(80.dp), height = 80.dp)
        }
        // Verdict placeholder
        ShimmerLine(modifier = Modifier.fillMaxWidth(), height = 60.dp)
        // Timeline placeholder
        ShimmerLine(modifier = Modifier.fillMaxWidth(0.9f), height = 24.dp)
        ShimmerLine(modifier = Modifier.fillMaxWidth(0.85f), height = 24.dp)
        ShimmerLine(modifier = Modifier.fillMaxWidth(0.8f), height = 24.dp)
        // Insight cards placeholder
        ShimmerLine(modifier = Modifier.fillMaxWidth(), height = 80.dp)
    }
}

/**
 * EmotionalPulseRing — hero element.
 * Кольцо пульсирует по arousal, цвет по valence, emoji по dominant emotion.
 */
@Composable
private fun EmotionalPulseRing(
    emotionInfo: EmotionInfo?,
    arousal: Float,
) {
    val ringColor = if (emotionInfo != null) valenceColor(emotionInfo.valence) else ColorIndigo
    val emoji = if (emotionInfo != null) emotionEmoji(emotionInfo.primary) else "\uD83D\uDCAD"
    val label = arousalLabel(arousal)

    // Pulsation speed tied to arousal: calm=slow, energetic=fast
    val pulseDuration = (2000 - (arousal * 1000).toInt()).coerceIn(800, 2000)
    val infiniteTransition = rememberInfiniteTransition(label = "pulse_ring")
    val scale by infiniteTransition.animateFloat(
        initialValue = 1.0f,
        targetValue = 1.15f,
        animationSpec = infiniteRepeatable(
            animation = tween(pulseDuration),
            repeatMode = RepeatMode.Reverse,
        ),
        label = "ring_scale",
    )
    val ringAlpha by infiniteTransition.animateFloat(
        initialValue = 0.7f,
        targetValue = 1.0f,
        animationSpec = infiniteRepeatable(
            animation = tween(pulseDuration),
            repeatMode = RepeatMode.Reverse,
        ),
        label = "ring_alpha",
    )

    Column(
        modifier = Modifier.fillMaxWidth(),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Box(
            contentAlignment = Alignment.Center,
            modifier = Modifier.size(96.dp),
        ) {
            // Pulsating ring
            Canvas(
                modifier = Modifier
                    .size(88.dp)
                    .scale(scale),
            ) {
                drawCircle(
                    color = ringColor.copy(alpha = ringAlpha * 0.3f),
                    radius = size.minDimension / 2,
                )
                drawCircle(
                    color = ringColor.copy(alpha = ringAlpha),
                    radius = size.minDimension / 2,
                    style = Stroke(width = 3.dp.toPx()),
                )
            }
            // Emoji center
            Text(
                text = emoji,
                fontSize = 36.sp,
            )
        }
        Spacer(modifier = Modifier.height(8.dp))
        Text(
            text = label,
            style = MaterialTheme.typography.titleSmall,
            color = ringColor,
            fontWeight = FontWeight.Medium,
        )
        if (emotionInfo != null) {
            Text(
                text = emotionInfo.primary.replaceFirstChar { it.uppercase() } +
                    (emotionInfo.secondary?.let { " + ${it.replaceFirstChar { c -> c.uppercase() }}" } ?: ""),
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
    }
}

/**
 * VerdictHeroCard — verdict с gradient border и expandable quotes.
 */
@Composable
private fun VerdictHeroCard(
    verdictText: String,
    quotes: List<String>,
    emotionalArc: String?,
) {
    var showQuotes by remember { mutableStateOf(false) }
    val gradientBrush = Brush.linearGradient(listOf(ColorIndigo, ColorTeal))

    Box(
        modifier = Modifier
            .fillMaxWidth()
            .drawBehind {
                drawRoundRect(
                    brush = gradientBrush,
                    cornerRadius = CornerRadius(16.dp.toPx()),
                    style = Stroke(width = 2.dp.toPx()),
                )
            }
            .padding(2.dp),
    ) {
        Card(
            modifier = Modifier.fillMaxWidth(),
            shape = RoundedCornerShape(14.dp),
            colors = CardDefaults.cardColors(
                containerColor = MaterialTheme.colorScheme.surfaceVariant,
            ),
        ) {
            Column(modifier = Modifier.padding(16.dp)) {
                Text(
                    text = verdictText,
                    style = MaterialTheme.typography.bodyLarge,
                    color = MaterialTheme.colorScheme.onSurface,
                )
                emotionalArc?.let { arc ->
                    Spacer(modifier = Modifier.height(6.dp))
                    Text(
                        text = arc,
                        style = MaterialTheme.typography.bodySmall,
                        color = ColorIndigo,
                        fontStyle = FontStyle.Italic,
                    )
                }
                if (quotes.isNotEmpty()) {
                    Spacer(modifier = Modifier.height(8.dp))
                    TextButton(
                        onClick = { showQuotes = !showQuotes },
                    ) {
                        Text(
                            text = if (showQuotes) "Скрыть цитаты" else "Показать цитаты (${quotes.size})",
                            style = MaterialTheme.typography.labelSmall,
                            color = ColorIndigo,
                        )
                    }
                    AnimatedVisibility(
                        visible = showQuotes,
                        enter = expandVertically() + fadeIn(),
                        exit = shrinkVertically(),
                    ) {
                        Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                            quotes.forEach { quote ->
                                Row {
                                    Box(
                                        modifier = Modifier
                                            .width(2.dp)
                                            .height(40.dp)
                                            .background(ColorIndigo),
                                    )
                                    Spacer(modifier = Modifier.width(8.dp))
                                    Text(
                                        text = "\"$quote\"",
                                        style = MaterialTheme.typography.bodySmall,
                                        fontStyle = FontStyle.Italic,
                                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                                        maxLines = 3,
                                        overflow = TextOverflow.Ellipsis,
                                    )
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}

/**
 * DayJourneyTimeline — вертикальная timeline с цветными точками.
 * Staggered появление сверху вниз.
 */
@Composable
private fun DayJourneyTimeline(points: List<AskDayMapPoint>) {
    Column(modifier = Modifier.fillMaxWidth()) {
        Text(
            text = "Путь дня",
            style = MaterialTheme.typography.titleSmall,
            fontWeight = FontWeight.Bold,
            modifier = Modifier.padding(bottom = 8.dp),
        )
        points.forEachIndexed { index, point ->
            var visible by remember { mutableStateOf(false) }
            LaunchedEffect(Unit) {
                delay(100L * index)
                visible = true
            }
            val alpha by animateFloatAsState(
                targetValue = if (visible) 1f else 0f,
                animationSpec = tween(400),
                label = "timeline_fade_$index",
            )

            val dotColor = when (point.label.lowercase()) {
                "peak" -> ColorTeal
                "valley" -> ColorRose
                "fork" -> ColorAmber
                else -> ColorIndigo
            }

            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(start = 4.dp),
                verticalAlignment = Alignment.Top,
            ) {
                // Dot + line column
                Column(
                    horizontalAlignment = Alignment.CenterHorizontally,
                    modifier = Modifier.width(24.dp),
                ) {
                    // Colored dot
                    Box(
                        modifier = Modifier
                            .size(12.dp)
                            .background(dotColor.copy(alpha = alpha), CircleShape),
                    )
                    // Dashed line to next point
                    if (index < points.size - 1) {
                        Canvas(
                            modifier = Modifier
                                .width(2.dp)
                                .height(40.dp),
                        ) {
                            drawLine(
                                color = Color(0xFF3D4450).copy(alpha = alpha),
                                start = Offset(size.width / 2, 0f),
                                end = Offset(size.width / 2, size.height),
                                strokeWidth = 1.dp.toPx(),
                                pathEffect = PathEffect.dashPathEffect(
                                    floatArrayOf(6f, 4f),
                                ),
                            )
                        }
                    }
                }
                // Content
                Column(
                    modifier = Modifier
                        .weight(1f)
                        .padding(start = 8.dp, bottom = if (index < points.size - 1) 4.dp else 0.dp),
                ) {
                    Row(
                        horizontalArrangement = Arrangement.spacedBy(6.dp),
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        if (point.time.isNotBlank()) {
                            Text(
                                text = point.time,
                                style = MaterialTheme.typography.labelSmall,
                                color = dotColor.copy(alpha = alpha),
                                fontWeight = FontWeight.Bold,
                            )
                        }
                        if (point.emotion.isNotBlank()) {
                            Text(
                                text = point.emotion,
                                style = MaterialTheme.typography.labelSmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = alpha * 0.7f),
                            )
                        }
                    }
                    if (point.text.isNotBlank()) {
                        Text(
                            text = point.text,
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurface.copy(alpha = alpha),
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
 * EmotionRiver — горизонтальные animated pills с эмоциями.
 */
@Composable
private fun EmotionRiver(
    emotionInfo: EmotionInfo?,
    emotionsList: List<String>,
) {
    var visible by remember { mutableStateOf(false) }
    LaunchedEffect(Unit) { visible = true }

    AnimatedVisibility(
        visible = visible,
        enter = slideInHorizontally(initialOffsetX = { it / 3 }) + fadeIn(tween(500)),
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .horizontalScroll(rememberScrollState()),
            horizontalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            // Structured emotion info (primary + secondary)
            if (emotionInfo != null) {
                EmotionPill(
                    text = emotionInfo.primary,
                    color = emotionColor(emotionInfo.primary),
                    isPrimary = true,
                )
                emotionInfo.secondary?.let { sec ->
                    EmotionPill(
                        text = sec,
                        color = emotionColor(sec),
                        isPrimary = false,
                    )
                }
            }
            // Legacy emotions list (if no structured info)
            if (emotionInfo == null) {
                emotionsList.forEachIndexed { idx, emotion ->
                    EmotionPill(
                        text = emotion,
                        color = emotionColor(emotion),
                        isPrimary = idx == 0,
                    )
                }
            }
        }
    }
}

@Composable
private fun EmotionPill(text: String, color: Color, isPrimary: Boolean) {
    Surface(
        shape = RoundedCornerShape(20.dp),
        color = color.copy(alpha = if (isPrimary) 0.18f else 0.10f),
    ) {
        Row(
            modifier = Modifier.padding(
                horizontal = if (isPrimary) 14.dp else 10.dp,
                vertical = if (isPrimary) 8.dp else 6.dp,
            ),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(4.dp),
        ) {
            Text(
                text = emotionEmoji(text),
                fontSize = if (isPrimary) 16.sp else 13.sp,
            )
            Text(
                text = text.replaceFirstChar { it.uppercase() },
                style = if (isPrimary) MaterialTheme.typography.labelLarge else MaterialTheme.typography.labelSmall,
                color = color,
                fontWeight = if (isPrimary) FontWeight.Bold else FontWeight.Normal,
            )
        }
    }
}

/**
 * InsightCarousel — горизонтальный свайп карточек с инсайтами.
 * 5 разных перспектив на день от разных "ролей".
 */
@Composable
private fun InsightCarousel(insights: List<InsightItem>) {
    Column {
        Text(
            text = "Перспективы",
            style = MaterialTheme.typography.titleSmall,
            fontWeight = FontWeight.Bold,
            modifier = Modifier.padding(bottom = 8.dp),
        )
        LazyRow(
            horizontalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            items(insights) { insight ->
                Surface(
                    modifier = Modifier.width(260.dp),
                    shape = RoundedCornerShape(16.dp),
                    color = MaterialTheme.colorScheme.surface,
                    shadowElevation = 2.dp,
                ) {
                    Column(modifier = Modifier.padding(14.dp)) {
                        Row(
                            verticalAlignment = Alignment.CenterVertically,
                            horizontalArrangement = Arrangement.spacedBy(6.dp),
                        ) {
                            Text(
                                text = insightRoleIcon(insight.role),
                                fontSize = 20.sp,
                            )
                            Text(
                                text = insightRoleLabel(insight.role),
                                style = MaterialTheme.typography.labelMedium,
                                fontWeight = FontWeight.Bold,
                                color = ColorIndigo,
                            )
                        }
                        Spacer(modifier = Modifier.height(8.dp))
                        Text(
                            text = insight.text,
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurface,
                            maxLines = 5,
                            overflow = TextOverflow.Ellipsis,
                        )
                    }
                }
            }
        }
        // Page indicator dots
        if (insights.size > 1) {
            Spacer(modifier = Modifier.height(8.dp))
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.Center,
            ) {
                insights.forEachIndexed { idx, _ ->
                    Box(
                        modifier = Modifier
                            .padding(horizontal = 3.dp)
                            .size(if (idx == 0) 8.dp else 6.dp)
                            .background(
                                color = if (idx == 0) ColorIndigo else ColorIndigo.copy(alpha = 0.3f),
                                shape = CircleShape,
                            ),
                    )
                }
            }
        }
    }
}

/**
 * PatternSignalRow — новизна и повторения.
 * Amber accent border для привлечения внимания к паттернам.
 */
@Composable
private fun PatternSignalRow(
    novelty: NoveltyInfo?,
    repetitions: RepetitionsInfo?,
) {
    Card(
        modifier = Modifier
            .fillMaxWidth()
            .drawBehind {
                drawRoundRect(
                    color = Color(0xFFFFB74D),
                    cornerRadius = CornerRadius(12.dp.toPx()),
                    style = Stroke(width = 1.dp.toPx()),
                )
            },
        shape = RoundedCornerShape(12.dp),
        colors = CardDefaults.cardColors(
            containerColor = ColorAmber.copy(alpha = 0.06f),
        ),
    ) {
        Column(modifier = Modifier.padding(12.dp)) {
            // Novelty
            novelty?.let { nov ->
                if (nov.newTopics.isNotEmpty() && nov.score > 0.3f) {
                    Row(
                        verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.spacedBy(6.dp),
                    ) {
                        Text(text = "\u2728", fontSize = 16.sp) // sparkle
                        Text(
                            text = "Новое в вашей жизни: ${nov.newTopics.joinToString(", ")}",
                            style = MaterialTheme.typography.bodySmall,
                            color = ColorTeal,
                            fontWeight = FontWeight.Medium,
                        )
                    }
                }
            }
            // Repetitions
            repetitions?.let { rep ->
                rep.items.filter { it.streakDays > 2 }.forEach { item ->
                    if (novelty != null && novelty.newTopics.isNotEmpty()) {
                        Spacer(modifier = Modifier.height(6.dp))
                    }
                    Row(
                        verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.spacedBy(6.dp),
                    ) {
                        Text(text = "\uD83D\uDD04", fontSize = 16.sp) // repeat icon
                        Text(
                            text = "\"${item.topic}\" уже ${item.streakDays} дней подряд",
                            style = MaterialTheme.typography.bodySmall,
                            color = ColorAmber,
                        )
                    }
                }
                rep.alertText?.let { alert ->
                    Spacer(modifier = Modifier.height(4.dp))
                    Text(
                        text = alert,
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        fontStyle = FontStyle.Italic,
                    )
                }
            }
        }
    }
}

// ──────────────────────────────────────────────
// Existing composables (updated/preserved)
// ──────────────────────────────────────────────

@Composable
private fun ConfidenceLine(label: String, evidenceCount: Int) {
    val color = confidenceColor(label)
    val text = when {
        evidenceCount == 0 -> "Записей пока нет. Нажмите «Запись», чтобы начать."
        evidenceCount == 1 -> "Ответ основан на 1 событии, уверенность ${confidenceHumanLabel(label)}"
        else -> "Ответ основан на $evidenceCount событиях, уверенность ${confidenceHumanLabel(label)}"
    }
    Text(
        text = text,
        style = MaterialTheme.typography.bodySmall,
        color = color,
    )
}

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
                    containerColor = ColorIndigo.copy(alpha = 0.1f),
                    labelColor = ColorIndigo,
                ),
            )
        }
        emotions.forEach { emotion ->
            SuggestionChip(
                onClick = {},
                label = { Text(emotion, style = MaterialTheme.typography.labelSmall) },
                colors = SuggestionChipDefaults.suggestionChipColors(
                    containerColor = ColorAmber.copy(alpha = 0.1f),
                    labelColor = ColorAmber,
                ),
            )
        }
    }
}

@Composable
private fun AskMicroStepCard(step: MicroStepInfo) {
    var showWhy by remember { mutableStateOf(false) }

    Card(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(12.dp),
        colors = CardDefaults.cardColors(
            containerColor = ColorTeal.copy(alpha = 0.08f),
        ),
    ) {
        Column(modifier = Modifier.padding(12.dp)) {
            Row(
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(6.dp),
            ) {
                Text(text = "\uD83D\uDE80", fontSize = 16.sp) // rocket
                Text(
                    text = "Микрошаг на завтра",
                    style = MaterialTheme.typography.labelMedium,
                    fontWeight = FontWeight.Bold,
                    color = ColorTeal,
                )
            }
            Spacer(modifier = Modifier.height(4.dp))
            Text(
                text = step.action,
                style = MaterialTheme.typography.bodyMedium,
            )
            if (step.why.isNotBlank()) {
                Spacer(modifier = Modifier.height(4.dp))
                Text(
                    text = if (showWhy) "Скрыть" else "Почему?",
                    style = MaterialTheme.typography.labelSmall,
                    color = ColorTeal,
                    modifier = Modifier.clickable { showWhy = !showWhy },
                )
                AnimatedVisibility(
                    visible = showWhy,
                    enter = expandVertically() + fadeIn(),
                    exit = shrinkVertically(),
                ) {
                    Text(
                        text = step.why,
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        modifier = Modifier.padding(top = 4.dp),
                    )
                }
            }
        }
    }
}

/**
 * ConfidenceBadge — preserved for backward compatibility.
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
