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

private val ColorHigh = Color(0xFF4CAF50)      // green — прямой ответ
private val ColorMedium = Color(0xFF2196F3)    // blue  — аккуратный ответ
private val ColorLow = Color(0xFFFF9800)       // amber — есть признаки
private val ColorSpeculative = Color(0xFFF44336) // red — требует уточнения

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

// ──────────────────────────────────────────────
// Data classes
// ──────────────────────────────────────────────

private data class EvidenceMeta(
    val id: String,
    val timestamp: String,
    val sentimentScore: Double,
    val topTopic: String,
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
)

private sealed class AskState {
    object Idle : AskState()
    object Loading : AskState()
    data class Success(val result: AskResult) : AskState()
    data class Error(val message: String) : AskState()
}

// ──────────────────────────────────────────────
// HTTP
// ──────────────────────────────────────────────

private val httpClient = OkHttpClient.Builder()
    .connectTimeout(10, TimeUnit.SECONDS)
    .readTimeout(30, TimeUnit.SECONDS)  // /ask может занять до ~400ms, даём запас
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

        // Парсим evidence_metadata и ui_hint из data[0]
        var uiHint = "timeline"
        val evidenceMetadata = mutableListOf<EvidenceMeta>()
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
 *   POST /ask → orchestrator сам выберет тул(ы) и вернёт синтезированный ответ.
 *   Аналогия: Google — одна строка, не "введи запрос в /search/events или /digest/daily".
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
            placeholder = { Text("Спроси что угодно о своём дне…") },
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

                // Warning banner
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

                // Confidence badge (пульсирует при speculative)
                ConfidenceBadge(label = r.confidenceLabel, confidence = r.confidence)
                Spacer(modifier = Modifier.height(8.dp))

                // Answer
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

                // EvidenceTrace — горизонтальная лента улик
                if (r.evidenceMetadata.isNotEmpty()) {
                    EvidenceTraceRow(r.evidenceMetadata)
                    Spacer(modifier = Modifier.height(8.dp))
                }

                // Expandable details
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
                            DetailRow("Тулы", r.toolsUsed.joinToString(", ").ifEmpty { "—" })
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

/**
 * ConfidenceBadge — chip с пульсирующей анимацией для speculative результатов.
 * ПОЧЕМУ пульсация: speculative = система не уверена → визуальный сигнал "уточни вопрос".
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
 * [14:32 · стресс · 🔴] [15:10 · работа · 🟡] [16:45 · финансы · 🟢]
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
    // Цвет dot по sentiment_score (0–1 → красный–жёлтый–зелёный)
    val dotColor = when {
        ev.sentimentScore >= 0.7 -> ColorHigh
        ev.sentimentScore >= 0.4 -> ColorLow
        else -> ColorSpeculative
    }
    // Извлекаем HH:MM из ISO-timestamp "2026-03-03T14:32:00" или "2026-03-03 14:32:00"
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
