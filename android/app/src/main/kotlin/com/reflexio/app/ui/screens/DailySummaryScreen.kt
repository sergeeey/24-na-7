package com.reflexio.app.ui.screens

import android.app.DatePickerDialog
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
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.ArrowBackIosNew
import androidx.compose.material.icons.rounded.ArrowForwardIos
import androidx.compose.material.icons.rounded.CalendarMonth
import androidx.compose.material.icons.rounded.LocationOn
import androidx.compose.material.icons.rounded.Refresh
import androidx.compose.material.icons.rounded.Shield
import androidx.compose.material.icons.rounded.TrendingUp
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.shadow
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.reflexio.app.data.calendar.CalendarReader
import com.reflexio.app.data.db.RecordingDatabase
import com.reflexio.app.data.model.CachedCalendarEvent
import com.reflexio.app.domain.network.ActionItemData
import com.reflexio.app.domain.network.DailyDigestData
import com.reflexio.app.domain.network.MemoryApi
import com.reflexio.app.domain.network.ServerEndpointResolver
import com.reflexio.app.ui.permissions.CalendarPermissionGate
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.time.LocalDate
import java.time.ZoneId

// ── Design System: Light, Premium, Unique ──
// WHY: warm off-white instead of pure white — feels organic, less clinical.
// Coral+indigo palette is rare in productivity apps (most use blue/green).
private val PageBg = Color(0xFFF7F5F2)
private val CardWhite = Color(0xFFFFFFFF)
private val TextPrimary = Color(0xFF1A1A2E)
private val TextSecondary = Color(0xFF6B7280)
private val TextMuted = Color(0xFF9CA3AF)
private val Coral = Color(0xFFFF6B6B)
private val CoralSoft = Color(0xFFFFF0F0)
private val Indigo = Color(0xFF6366F1)
private val IndigoSoft = Color(0xFFF0F0FF)
private val Mint = Color(0xFF34D399)
private val MintSoft = Color(0xFFECFDF5)
private val Amber = Color(0xFFF59E0B)
private val AmberSoft = Color(0xFFFFFBEB)
private val Slate = Color(0xFF475569)

private sealed class DigestUiState {
    object Loading : DigestUiState()
    data class Success(val data: DailyDigestData) : DigestUiState()
    data class Error(val message: String) : DigestUiState()
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
fun DailySummaryScreen(
    modifier: Modifier = Modifier,
    baseHttpUrl: String,
) {
    val context = LocalContext.current
    var selectedDate by remember { mutableStateOf(LocalDate.now()) }
    var retryKey by remember { mutableStateOf(0) }
    var state by remember { mutableStateOf<DigestUiState>(DigestUiState.Loading) }
    var calendarEvents by remember { mutableStateOf<List<CachedCalendarEvent>>(emptyList()) }
    var calendarGranted by remember { mutableStateOf(false) }

    LaunchedEffect(baseHttpUrl, selectedDate, retryKey) {
        state = DigestUiState.Loading
        state = try {
            val result = withContext(Dispatchers.IO) {
                MemoryApi.fetchDigest(baseHttpUrl, selectedDate.toString())
            }
            DigestUiState.Success(result)
        } catch (e: Exception) {
            DigestUiState.Error(ServerEndpointResolver.userFacingError(e.message, baseHttpUrl))
        }
    }

    LaunchedEffect(selectedDate, calendarGranted) {
        if (!calendarGranted) return@LaunchedEffect
        calendarEvents = withContext(Dispatchers.IO) {
            try {
                val zone = ZoneId.systemDefault()
                val dayStart = selectedDate.atStartOfDay(zone).toInstant().toEpochMilli()
                val dayEnd = selectedDate.plusDays(1).atStartOfDay(zone).toInstant().toEpochMilli()
                val db = RecordingDatabase.getInstance(context)
                val lastSync = db.calendarCacheDao().lastSyncTime() ?: 0L
                if (System.currentTimeMillis() - lastSync > 5 * 60_000) {
                    val fresh = CalendarReader.readEvents(context.contentResolver)
                    db.calendarCacheDao().insertAll(fresh)
                }
                db.calendarCacheDao().eventsForDay(dayStart, dayEnd)
            } catch (_: Exception) { emptyList() }
        }
    }

    val datePicker = remember {
        DatePickerDialog(context, { _, y, m, d -> selectedDate = LocalDate.of(y, m + 1, d) },
            selectedDate.year, selectedDate.monthValue - 1, selectedDate.dayOfMonth)
    }

    Column(
        modifier = modifier
            .fillMaxSize()
            .background(PageBg)
            .verticalScroll(rememberScrollState())
            .padding(20.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        // ── Header ──
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Column {
                Text("Итог", fontSize = 32.sp, fontWeight = FontWeight.Black, color = TextPrimary)
                Text(
                    if (selectedDate == LocalDate.now()) "Сегодня" else selectedDate.toString(),
                    fontSize = 14.sp, color = TextMuted,
                )
            }
            Surface(
                shape = CircleShape,
                color = CardWhite,
                shadowElevation = 2.dp,
            ) {
                IconButton(onClick = { retryKey++ }) {
                    Icon(Icons.Rounded.Refresh, contentDescription = null, tint = Indigo)
                }
            }
        }

        // ── Date Picker ──
        Surface(
            shape = RoundedCornerShape(20.dp),
            color = CardWhite,
            shadowElevation = 1.dp,
        ) {
            Row(
                modifier = Modifier.fillMaxWidth().padding(6.dp),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically,
            ) {
                IconButton(onClick = { selectedDate = selectedDate.minusDays(1) }) {
                    Icon(Icons.Rounded.ArrowBackIosNew, contentDescription = null, tint = Slate, modifier = Modifier.size(18.dp))
                }
                Surface(
                    onClick = { datePicker.show() },
                    shape = RoundedCornerShape(14.dp),
                    color = IndigoSoft,
                ) {
                    Row(
                        modifier = Modifier.padding(horizontal = 16.dp, vertical = 10.dp),
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        Icon(Icons.Rounded.CalendarMonth, contentDescription = null, tint = Indigo, modifier = Modifier.size(18.dp))
                        Spacer(Modifier.width(8.dp))
                        Text(
                            if (selectedDate == LocalDate.now()) "Сегодня" else selectedDate.toString(),
                            fontWeight = FontWeight.SemiBold, color = Indigo, fontSize = 14.sp,
                        )
                    }
                }
                IconButton(onClick = { selectedDate = selectedDate.plusDays(1) }) {
                    Icon(Icons.Rounded.ArrowForwardIos, contentDescription = null, tint = Slate, modifier = Modifier.size(18.dp))
                }
            }
        }

        CalendarPermissionGate(onGranted = { calendarGranted = true })

        when (val current = state) {
            DigestUiState.Loading -> {
                Box(Modifier.fillMaxWidth().height(200.dp), contentAlignment = Alignment.Center) {
                    CircularProgressIndicator(color = Indigo, strokeWidth = 3.dp)
                }
            }
            is DigestUiState.Error -> {
                Surface(shape = RoundedCornerShape(16.dp), color = CoralSoft) {
                    Text(current.message, modifier = Modifier.padding(16.dp), color = Coral, fontSize = 14.sp)
                }
            }
            is DigestUiState.Success -> {
                DigestBodyV2(current.data, calendarEvents)
            }
        }

        Spacer(Modifier.height(80.dp))
    }
}

// ── Quick Stats ──

@Composable
private fun DigestBodyV2(data: DailyDigestData, calendarEvents: List<CachedCalendarEvent>) {

    // Stats row
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
        GlassStatCard("${data.totalRecordings}", "записей", Coral, CoralSoft, Modifier.weight(1f))
        GlassStatCard(data.totalDuration, "аудио", Indigo, IndigoSoft, Modifier.weight(1f))
        GlassStatCard("${data.threadCount}", "потоков", Amber, AmberSoft, Modifier.weight(1f))
        GlassStatCard("${(data.trustedFraction * 100).toInt()}%", "доверие",
            if (data.trustedFraction >= 0.3f) Mint else Coral,
            if (data.trustedFraction >= 0.3f) MintSoft else CoralSoft,
            Modifier.weight(1f))
    }

    // Locations
    if (data.locations.isNotEmpty()) {
        Surface(shape = RoundedCornerShape(16.dp), color = CardWhite, shadowElevation = 1.dp) {
            Row(Modifier.padding(14.dp).fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                Box(
                    modifier = Modifier.size(32.dp).clip(RoundedCornerShape(10.dp)).background(AmberSoft),
                    contentAlignment = Alignment.Center,
                ) {
                    Icon(Icons.Rounded.LocationOn, contentDescription = null, tint = Amber, modifier = Modifier.size(18.dp))
                }
                Spacer(Modifier.width(12.dp))
                Text(data.locations.joinToString(" → "), color = TextPrimary, fontSize = 14.sp, maxLines = 1, overflow = TextOverflow.Ellipsis)
            }
        }
    }

    // Evidence
    if (data.totalRecordings > 0) {
        EvidenceCard(data)
    }

    // Summary
    if (data.summaryText.isNotBlank() && data.summaryText != "Нет записей за день.") {
        SummaryCard(data)
    } else if (data.totalRecordings == 0) {
        EmptyCard()
    }

    // Verdict
    data.verdict?.let { verdict ->
        Surface(shape = RoundedCornerShape(16.dp), color = IndigoSoft, shadowElevation = 0.dp) {
            Row(Modifier.padding(14.dp), verticalAlignment = Alignment.CenterVertically) {
                Box(
                    modifier = Modifier.size(28.dp).clip(CircleShape).background(
                        Brush.linearGradient(listOf(Indigo, Color(0xFF818CF8)))
                    ),
                    contentAlignment = Alignment.Center,
                ) {
                    Icon(Icons.Rounded.TrendingUp, contentDescription = null, tint = Color.White, modifier = Modifier.size(16.dp))
                }
                Spacer(Modifier.width(12.dp))
                Text(verdict, color = Indigo, fontSize = 14.sp, fontWeight = FontWeight.Medium)
            }
        }
    }

    // Calendar
    if (calendarEvents.isNotEmpty()) {
        CalendarCard(calendarEvents)
    }

    // Themes + Novelty
    if (data.keyThemes.isNotEmpty() || data.novelty.isNotEmpty()) {
        ThemesBlock(data.keyThemes, data.novelty)
    }

    // Emotions
    if (data.emotions.isNotEmpty()) {
        EmotionsBlock(data.emotions)
    }

    // Actions
    if (data.actions.isNotEmpty()) {
        ActionsBlock(data.actions)
    }

    // Consumed content — what user watched/listened to
    if (data.consumedCount > 0) {
        ConsumedContentCard(data)
    }
}

// ── Glass Stat Card ──

@Composable
private fun GlassStatCard(value: String, label: String, accent: Color, bg: Color, modifier: Modifier = Modifier) {
    Surface(
        modifier = modifier,
        shape = RoundedCornerShape(16.dp),
        color = bg,
        shadowElevation = 0.dp,
    ) {
        Column(
            modifier = Modifier.padding(vertical = 14.dp, horizontal = 6.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            Text(value, fontSize = 20.sp, fontWeight = FontWeight.Black, color = accent)
            Text(label, fontSize = 11.sp, color = accent.copy(alpha = 0.6f), fontWeight = FontWeight.Medium)
        }
    }
}

// ── Evidence Card ──

@Composable
private fun EvidenceCard(data: DailyDigestData) {
    Surface(shape = RoundedCornerShape(16.dp), color = CardWhite, shadowElevation = 1.dp) {
        Column(Modifier.padding(16.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Box(
                    modifier = Modifier.size(28.dp).clip(RoundedCornerShape(8.dp))
                        .background(if (data.degraded) CoralSoft else MintSoft),
                    contentAlignment = Alignment.Center,
                ) {
                    Icon(Icons.Rounded.Shield, contentDescription = null,
                        tint = if (data.degraded) Coral else Mint, modifier = Modifier.size(16.dp))
                }
                Spacer(Modifier.width(10.dp))
                Text(
                    if (data.degraded) "Неполный контекст" else "Полный контекст",
                    fontWeight = FontWeight.SemiBold, fontSize = 14.sp,
                    color = if (data.degraded) Coral else Mint,
                )
            }
            Spacer(Modifier.height(12.dp))
            @Suppress("DEPRECATION")
            LinearProgressIndicator(
                progress = data.evidenceStrength.coerceIn(0f, 1f),
                modifier = Modifier.fillMaxWidth().height(8.dp).clip(RoundedCornerShape(4.dp)),
                color = if (data.evidenceStrength >= 0.5f) Mint else Amber,
                trackColor = Color(0xFFF1F5F9),
            )
            Spacer(Modifier.height(10.dp))
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                MiniStat("Источников", "${data.sourcesCount}")
                MiniStat("Эпизодов", "${data.episodesUsed}")
                MiniStat("Потоков", "${data.longThreadCount}")
            }
        }
    }
}

@Composable
private fun MiniStat(label: String, value: String) {
    Column(horizontalAlignment = Alignment.CenterHorizontally) {
        Text(value, fontWeight = FontWeight.Bold, fontSize = 16.sp, color = TextPrimary)
        Text(label, fontSize = 11.sp, color = TextMuted)
    }
}

// ── Summary Card ──

@Composable
private fun SummaryCard(data: DailyDigestData) {
    Surface(shape = RoundedCornerShape(20.dp), color = CardWhite, shadowElevation = 2.dp) {
        Column(Modifier.padding(20.dp)) {
            Text("Сводка дня", fontWeight = FontWeight.Bold, fontSize = 18.sp, color = TextPrimary)
            Spacer(Modifier.height(10.dp))
            Text(data.summaryText, fontSize = 15.sp, color = TextSecondary, lineHeight = 22.sp)
        }
    }
}

@Composable
private fun EmptyCard() {
    Surface(shape = RoundedCornerShape(20.dp), color = CardWhite, shadowElevation = 1.dp) {
        Column(
            Modifier.padding(32.dp).fillMaxWidth(),
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            Text("🌅", fontSize = 40.sp)
            Spacer(Modifier.height(12.dp))
            Text("Пока нет записей", fontWeight = FontWeight.SemiBold, fontSize = 16.sp, color = TextPrimary)
            Spacer(Modifier.height(4.dp))
            Text("Записи появятся после начала записи", fontSize = 13.sp, color = TextMuted, textAlign = TextAlign.Center)
        }
    }
}

// ── Calendar ──

@Composable
private fun CalendarCard(events: List<CachedCalendarEvent>) {
    Surface(shape = RoundedCornerShape(16.dp), color = CardWhite, shadowElevation = 1.dp) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Box(
                    modifier = Modifier.size(28.dp).clip(RoundedCornerShape(8.dp)).background(IndigoSoft),
                    contentAlignment = Alignment.Center,
                ) {
                    Icon(Icons.Rounded.CalendarMonth, contentDescription = null, tint = Indigo, modifier = Modifier.size(16.dp))
                }
                Spacer(Modifier.width(10.dp))
                Text("Встречи · ${events.size}", fontWeight = FontWeight.SemiBold, fontSize = 14.sp, color = TextPrimary)
            }
            events.forEach { event ->
                val timeStr = if (event.allDay) "Весь день" else {
                    val s = java.time.Instant.ofEpochMilli(event.startMs).atZone(java.time.ZoneId.systemDefault())
                    val e = java.time.Instant.ofEpochMilli(event.endMs).atZone(java.time.ZoneId.systemDefault())
                    "${s.hour}:${"%02d".format(s.minute)}–${e.hour}:${"%02d".format(e.minute)}"
                }
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
                    Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.weight(1f)) {
                        Box(Modifier.size(6.dp).clip(CircleShape).background(Indigo))
                        Spacer(Modifier.width(10.dp))
                        Text(event.title, fontSize = 14.sp, color = TextPrimary, maxLines = 1, overflow = TextOverflow.Ellipsis)
                    }
                    Text(timeStr, fontSize = 12.sp, color = Indigo, fontWeight = FontWeight.Medium)
                }
            }
        }
    }
}

// ── Themes ──

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun ThemesBlock(themes: List<String>, novelty: List<String>) {
    Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
        Text("Темы дня", fontWeight = FontWeight.Bold, fontSize = 16.sp, color = TextPrimary)
        FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            themes.forEach { theme ->
                Pill(theme, Indigo, IndigoSoft)
            }
        }
        if (novelty.isNotEmpty()) {
            Spacer(Modifier.height(4.dp))
            Text("Новое сегодня", fontWeight = FontWeight.SemiBold, fontSize = 13.sp, color = Amber)
            FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                novelty.forEach { topic ->
                    Pill(topic, Amber, AmberSoft)
                }
            }
        }
    }
}

// ── Emotions ──

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun EmotionsBlock(emotions: List<String>) {
    Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
        Text("Эмоции", fontWeight = FontWeight.Bold, fontSize = 16.sp, color = TextPrimary)
        FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            emotions.forEach { emotion ->
                val (color, bg) = when {
                    emotion.contains("радость") || emotion.contains("энтузиазм") -> Mint to MintSoft
                    emotion.contains("тревога") || emotion.contains("раздражение") -> Coral to CoralSoft
                    emotion.contains("возбуждение") || emotion.contains("энергичность") -> Amber to AmberSoft
                    else -> Indigo to IndigoSoft
                }
                Pill(emotion, color, bg)
            }
        }
    }
}

// ── Actions ──

@Composable
private fun ActionsBlock(actions: List<ActionItemData>) {
    Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
        Text("Намерения", fontWeight = FontWeight.Bold, fontSize = 16.sp, color = TextPrimary)
        actions.forEach { action ->
            val dotColor = when (action.urgency) {
                "high" -> Coral
                "medium" -> Amber
                else -> Mint
            }
            Surface(shape = RoundedCornerShape(14.dp), color = CardWhite, shadowElevation = 1.dp) {
                Row(Modifier.padding(14.dp).fillMaxWidth(), verticalAlignment = Alignment.Top) {
                    Box(Modifier.padding(top = 6.dp).size(8.dp).clip(CircleShape).background(dotColor))
                    Spacer(Modifier.width(12.dp))
                    Column(Modifier.weight(1f)) {
                        Text(action.text, fontSize = 14.sp, color = TextPrimary)
                        Spacer(Modifier.height(2.dp))
                        Text(
                            if (action.done) "Выполнено" else action.urgency,
                            fontSize = 12.sp, fontWeight = FontWeight.Medium,
                            color = if (action.done) Mint else TextMuted,
                        )
                    }
                }
            }
        }
    }
}

// ── Consumed Content ──

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun ConsumedContentCard(data: DailyDigestData) {
    Surface(shape = RoundedCornerShape(18.dp), color = CardWhite, shadowElevation = 1.dp) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Box(
                    modifier = Modifier.size(28.dp).clip(RoundedCornerShape(8.dp)).background(Color(0xFFF5F3FF)),
                    contentAlignment = Alignment.Center,
                ) {
                    Text("📺", fontSize = 14.sp)
                }
                Spacer(Modifier.width(10.dp))
                Text("Что смотрел", fontWeight = FontWeight.Bold, fontSize = 15.sp, color = TextPrimary)
                Spacer(Modifier.weight(1f))
                Text("${data.consumedCount} фрагментов", fontSize = 12.sp, color = TextMuted)
            }

            // Source breakdown
            if (data.consumedSources.isNotEmpty()) {
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    data.consumedSources.forEach { (source, count) ->
                        val (label, color, bg) = when (source) {
                            "youtube" -> Triple("YouTube", Coral, CoralSoft)
                            "tv" -> Triple("TV", Indigo, IndigoSoft)
                            "podcast" -> Triple("Подкаст", Amber, AmberSoft)
                            else -> Triple("Другое", Color(0xFF9CA3AF), Color(0xFFF3F4F6))
                        }
                        Surface(shape = RoundedCornerShape(10.dp), color = bg) {
                            Row(Modifier.padding(horizontal = 10.dp, vertical = 6.dp), verticalAlignment = Alignment.CenterVertically) {
                                Text(label, fontSize = 12.sp, fontWeight = FontWeight.SemiBold, color = color)
                                Spacer(Modifier.width(4.dp))
                                Text("$count", fontSize = 12.sp, color = color.copy(alpha = 0.6f))
                            }
                        }
                    }
                }
            }

            // Topics from consumed content
            if (data.consumedTopics.isNotEmpty()) {
                FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    data.consumedTopics.take(6).forEach { topic ->
                        Pill(topic, Color(0xFF8B5CF6), Color(0xFFF5F3FF))
                    }
                }
            }
        }
    }
}

// ── Pill Component ──

@Composable
private fun Pill(text: String, accent: Color, bg: Color) {
    Surface(shape = RoundedCornerShape(12.dp), color = bg) {
        Text(
            text = text,
            modifier = Modifier.padding(horizontal = 14.dp, vertical = 7.dp),
            fontSize = 13.sp,
            fontWeight = FontWeight.Medium,
            color = accent,
        )
    }
}
