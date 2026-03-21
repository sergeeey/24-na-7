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
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.AutoAwesome
import androidx.compose.material.icons.rounded.Lightbulb
import androidx.compose.material.icons.rounded.People
import androidx.compose.material.icons.rounded.EditNote
import androidx.compose.material.icons.rounded.Search
import androidx.compose.material.icons.rounded.Verified
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextField
import androidx.compose.material3.TextFieldDefaults
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.reflexio.app.domain.network.AskResponseData
import com.reflexio.app.domain.network.MemoryApi
import com.reflexio.app.domain.network.ServerEndpointResolver
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

// ── Design System: Dark Glassmorphism (matches DailySummaryScreen / MirrorScreen) ──
private val PageBg = Color.Transparent
private val CardWhite = Color(0x1AFFFFFF)          // 10% white glass
private val TextPrimary = Color(0xFFFFFFFF)
private val TextSecondary = Color(0xFFA0AAB2)
private val TextMuted = Color(0xFF6B7C8A)
private val Coral = Color(0xFFFF6B6B)
private val CoralSoft = Color(0x26FF6B6B)
private val Indigo = Color(0xFF818CF8)
private val IndigoSoft = Color(0x26818CF8)
private val Mint = Color(0xFF34D399)
private val MintSoft = Color(0x2634D399)
private val Amber = Color(0xFFF59E0B)
private val AmberSoft = Color(0x26F59E0B)
private val Teal = Color(0xFF14B8A6)
private val TealSoft = Color(0x2614B8A6)

private sealed class AskUiState {
    object Idle : AskUiState()
    object Loading : AskUiState()
    data class Success(val result: AskResponseData) : AskUiState()
    data class Error(val message: String) : AskUiState()
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
fun AskScreen(
    baseHttpUrl: String,
    initialQuestion: String = "",
    onInitialQuestionConsumed: () -> Unit = {},
    onOpenSearch: (String) -> Unit = {},
    onOpenPeople: () -> Unit = {},
    modifier: Modifier = Modifier,
) {
    val scope = rememberCoroutineScope()
    var question by remember(initialQuestion) { mutableStateOf(initialQuestion) }
    var state by remember { mutableStateOf<AskUiState>(AskUiState.Idle) }
    var showNoteInput by remember { mutableStateOf(false) }
    var noteText by remember { mutableStateOf("") }
    var noteSaving by remember { mutableStateOf(false) }
    var noteResult by remember { mutableStateOf<String?>(null) }

    val samples = listOf(
        SampleQuery("Что было сегодня?", Icons.Rounded.Lightbulb, Indigo),
        SampleQuery("Что я обещал?", Icons.Rounded.Verified, Coral),
        SampleQuery("Какие паттерны?", Icons.Rounded.AutoAwesome, Amber),
        SampleQuery("Кто рядом?", Icons.Rounded.People, Mint),
    )

    fun submit(input: String) {
        val trimmed = input.trim()
        if (trimmed.isBlank()) return
        scope.launch {
            state = AskUiState.Loading
            state = try {
                val result = withContext(Dispatchers.IO) { MemoryApi.ask(baseHttpUrl, trimmed) }
                AskUiState.Success(result)
            } catch (e: Exception) {
                AskUiState.Error(ServerEndpointResolver.userFacingError(e.message, baseHttpUrl))
            }
        }
    }

    LaunchedEffect(initialQuestion) {
        if (initialQuestion.isNotBlank()) {
            question = initialQuestion
            submit(initialQuestion)
            onInitialQuestionConsumed()
        }
    }

    Column(
        modifier = modifier
            .fillMaxSize()
            .background(PageBg)
            .padding(20.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        // ── Header ──
        Text("Спросить", fontSize = 32.sp, fontWeight = FontWeight.Black, color = TextPrimary)
        Text(
            "Спроси о людях, обещаниях, паттернах или событиях дня",
            fontSize = 14.sp, color = TextMuted, lineHeight = 18.sp,
        )

        // ── Search bar ──
        Surface(
            shape = RoundedCornerShape(20.dp),
            color = CardWhite,
            shadowElevation = 2.dp,
        ) {
            TextField(
                value = question,
                onValueChange = { question = it },
                modifier = Modifier.fillMaxWidth(),
                placeholder = { Text("О чём спросить память?", color = TextMuted) },
                leadingIcon = {
                    Icon(Icons.Rounded.Search, contentDescription = null, tint = Indigo)
                },
                colors = TextFieldDefaults.colors(
                    focusedContainerColor = Color.Transparent,
                    unfocusedContainerColor = Color.Transparent,
                    focusedIndicatorColor = Color.Transparent,
                    unfocusedIndicatorColor = Color.Transparent,
                    cursorColor = Indigo,
                ),
                keyboardOptions = KeyboardOptions(imeAction = ImeAction.Search),
                keyboardActions = KeyboardActions(onSearch = { submit(question) }),
                singleLine = true,
            )
        }

        // ── Quick queries ──
        FlowRow(
            horizontalArrangement = Arrangement.spacedBy(8.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            samples.forEach { sample ->
                Surface(
                    onClick = { question = sample.text; submit(sample.text) },
                    shape = RoundedCornerShape(14.dp),
                    color = CardWhite,
                    shadowElevation = 1.dp,
                ) {
                    Row(
                        modifier = Modifier.padding(horizontal = 14.dp, vertical = 10.dp),
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        Icon(sample.icon, contentDescription = null, tint = sample.color, modifier = Modifier.size(16.dp))
                        Spacer(Modifier.width(6.dp))
                        Text(sample.text, fontSize = 13.sp, fontWeight = FontWeight.Medium, color = TextPrimary)
                    }
                }
            }
        }

        // ── Note input ──
        Surface(
            onClick = { showNoteInput = !showNoteInput; noteResult = null },
            shape = RoundedCornerShape(14.dp),
            color = if (showNoteInput) TealSoft else CardWhite,
            shadowElevation = 1.dp,
        ) {
            Row(
                modifier = Modifier.padding(horizontal = 14.dp, vertical = 10.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Icon(Icons.Rounded.EditNote, contentDescription = null, tint = Teal, modifier = Modifier.size(16.dp))
                Spacer(Modifier.width(6.dp))
                Text("Записать заметку", fontSize = 13.sp, fontWeight = FontWeight.Medium, color = TextPrimary)
            }
        }

        if (showNoteInput) {
            Surface(shape = RoundedCornerShape(20.dp), color = CardWhite, shadowElevation = 2.dp) {
                Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                    TextField(
                        value = noteText,
                        onValueChange = { noteText = it },
                        modifier = Modifier.fillMaxWidth(),
                        placeholder = { Text("Запишите мысль, инсайт или заметку...", color = TextMuted) },
                        colors = TextFieldDefaults.colors(
                            focusedContainerColor = Color.Transparent,
                            unfocusedContainerColor = Color.Transparent,
                            focusedIndicatorColor = Color.Transparent,
                            unfocusedIndicatorColor = Color.Transparent,
                            cursorColor = Teal,
                        ),
                        minLines = 2,
                        maxLines = 6,
                    )
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween,
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        noteResult?.let { msg ->
                            Text(msg, fontSize = 12.sp, color = if (msg.startsWith("✓")) Teal else Coral)
                        }
                        Spacer(Modifier.weight(1f))
                        Surface(
                            onClick = {
                                if (noteText.isBlank() || noteSaving) return@Surface
                                scope.launch {
                                    noteSaving = true
                                    noteResult = null
                                    val id = withContext(Dispatchers.IO) { MemoryApi.postNote(baseHttpUrl, noteText.trim()) }
                                    noteSaving = false
                                    if (id != null) {
                                        noteResult = "✓ Сохранено"
                                        noteText = ""
                                    } else {
                                        noteResult = "Ошибка сохранения"
                                    }
                                }
                            },
                            shape = RoundedCornerShape(12.dp),
                            color = if (noteSaving || noteText.isBlank()) TealSoft else Teal,
                        ) {
                            Row(Modifier.padding(horizontal = 16.dp, vertical = 8.dp), verticalAlignment = Alignment.CenterVertically) {
                                if (noteSaving) {
                                    CircularProgressIndicator(modifier = Modifier.size(14.dp), strokeWidth = 2.dp, color = Teal)
                                } else {
                                    Text("Сохранить", fontSize = 13.sp, fontWeight = FontWeight.SemiBold, color = if (noteText.isBlank()) Teal else Color.White)
                                }
                            }
                        }
                    }
                }
            }
        }

        // ── Result area ──
        when (val current = state) {
            AskUiState.Idle -> {
                Spacer(Modifier.height(24.dp))
                Column(
                    Modifier.fillMaxWidth(),
                    horizontalAlignment = Alignment.CenterHorizontally,
                ) {
                    Text("💭", fontSize = 48.sp)
                    Spacer(Modifier.height(8.dp))
                    Text(
                        "Задайте вопрос — память ответит",
                        fontSize = 15.sp, color = TextMuted, textAlign = TextAlign.Center,
                    )
                    Spacer(Modifier.height(20.dp))
                    androidx.compose.material3.Button(
                        onClick = { question = samples.first().text; submit(samples.first().text) },
                        shape = RoundedCornerShape(12.dp),
                    ) {
                        Text("Задать первый вопрос")
                    }
                }
            }
            AskUiState.Loading -> {
                Box(Modifier.fillMaxWidth().height(120.dp), contentAlignment = Alignment.Center) {
                    CircularProgressIndicator(color = Indigo, strokeWidth = 3.dp)
                }
            }
            is AskUiState.Error -> {
                Surface(shape = RoundedCornerShape(16.dp), color = CoralSoft) {
                    Text(current.message, modifier = Modifier.padding(16.dp), color = Coral, fontSize = 14.sp)
                }
            }
            is AskUiState.Success -> {
                AnswerView(current.result, onOpenSearch)
            }
        }
    }
}

// ── Answer View ──

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun AnswerView(result: AskResponseData, onOpenSearch: (String) -> Unit) {
    LazyColumn(verticalArrangement = Arrangement.spacedBy(12.dp)) {

        // Main answer
        item {
            Surface(shape = RoundedCornerShape(20.dp), color = CardWhite, shadowElevation = 2.dp) {
                Column(Modifier.padding(18.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                    Text(result.answer, fontSize = 16.sp, fontWeight = FontWeight.Medium, color = TextPrimary, lineHeight = 22.sp)

                    // Confidence bar
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        val confColor = when (result.confidenceLabel) {
                            "high" -> Mint
                            "medium" -> Indigo
                            "low" -> Amber
                            else -> Coral
                        }
                        val confLabel = when (result.confidenceLabel) {
                            "high" -> "Высокая"
                            "medium" -> "Средняя"
                            "low" -> "Низкая"
                            else -> "Неясно"
                        }
                        Box(Modifier.size(8.dp).clip(CircleShape).background(confColor))
                        Spacer(Modifier.width(8.dp))
                        Text("$confLabel · ${result.evidenceCount} улик", fontSize = 12.sp, color = confColor, fontWeight = FontWeight.SemiBold)
                    }

                    result.warning?.let { warning ->
                        Surface(shape = RoundedCornerShape(10.dp), color = AmberSoft) {
                            Text(
                                humanizeWarning(warning),
                                modifier = Modifier.padding(10.dp),
                                fontSize = 12.sp, color = Amber,
                            )
                        }
                    }
                }
            }
        }

        // Digest layer
        result.digest?.let { digest ->
            item {
                Surface(shape = RoundedCornerShape(18.dp), color = CardWhite, shadowElevation = 1.dp) {
                    Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                        SectionHeader("Дайджест", Indigo)
                        digest.summaryText?.let { Text(it, fontSize = 14.sp, color = TextSecondary) }
                        if (digest.keyThemes.isNotEmpty()) {
                            FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                                digest.keyThemes.take(4).forEach { theme ->
                                    PillClickable(theme, Indigo, IndigoSoft) { onOpenSearch(theme) }
                                }
                            }
                        }
                    }
                }
            }
        }

        // Events layer
        result.events?.let { events ->
            if (events.total > 0) {
                item {
                    Surface(shape = RoundedCornerShape(18.dp), color = CardWhite, shadowElevation = 1.dp) {
                        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                            SectionHeader("События · ${events.total}", Amber)
                            FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                                events.topTopics.forEach { topic ->
                                    PillClickable(topic, Amber, AmberSoft) { onOpenSearch(topic) }
                                }
                            }
                        }
                    }
                }
            }
        }

        // Evidence
        if (result.evidenceMetadata.isNotEmpty()) {
            item {
                SectionHeader("Улики", Mint)
            }
            items(result.evidenceMetadata, key = { it.id }) { evidence ->
                Surface(shape = RoundedCornerShape(14.dp), color = CardWhite, shadowElevation = 1.dp) {
                    Row(Modifier.padding(14.dp).fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                        Box(
                            modifier = Modifier.size(36.dp).clip(RoundedCornerShape(10.dp)).background(MintSoft),
                            contentAlignment = Alignment.Center,
                        ) {
                            Text(evidence.timestamp.take(5), fontSize = 10.sp, fontWeight = FontWeight.Bold, color = Mint)
                        }
                        Spacer(Modifier.width(12.dp))
                        Column(Modifier.weight(1f)) {
                            Text(
                                evidence.topTopic.ifBlank { "Событие" },
                                fontSize = 14.sp, fontWeight = FontWeight.Medium, color = TextPrimary,
                                maxLines = 1, overflow = TextOverflow.Ellipsis,
                            )
                            Text(evidence.timestamp, fontSize = 11.sp, color = TextMuted)
                        }
                    }
                }
            }
        }
    }
}

// ── Components ──

private data class SampleQuery(val text: String, val icon: ImageVector, val color: Color)

@Composable
private fun SectionHeader(title: String, color: Color) {
    Row(verticalAlignment = Alignment.CenterVertically) {
        Box(Modifier.size(4.dp, 16.dp).clip(RoundedCornerShape(2.dp)).background(color))
        Spacer(Modifier.width(8.dp))
        Text(title, fontWeight = FontWeight.Bold, fontSize = 15.sp, color = TextPrimary)
    }
}

@Composable
private fun PillClickable(text: String, accent: Color, bg: Color, onClick: () -> Unit) {
    Surface(onClick = onClick, shape = RoundedCornerShape(12.dp), color = bg) {
        Text(text, modifier = Modifier.padding(horizontal = 14.dp, vertical = 7.dp), fontSize = 13.sp, fontWeight = FontWeight.Medium, color = accent)
    }
}

private fun humanizeWarning(warning: String): String {
    val normalized = warning.lowercase()
    return if ("мало данных" in normalized || "недостаточно данных" in normalized) {
        "За этот период мало записей. Попробуй спросить за другой день или про конкретного человека."
    } else warning
}
