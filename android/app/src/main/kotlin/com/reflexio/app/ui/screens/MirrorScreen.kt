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
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.Favorite
import androidx.compose.material.icons.rounded.FitnessCenter
import androidx.compose.material.icons.rounded.Hotel
import androidx.compose.material.icons.rounded.Psychology
import androidx.compose.material.icons.rounded.SelfImprovement
import androidx.compose.material.icons.rounded.TrendingUp
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
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
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.reflexio.app.data.db.RecordingDatabase
import com.reflexio.app.data.health.HealthConnectReader
import com.reflexio.app.data.model.CachedHealthMetric
import com.reflexio.app.domain.network.InsightCard
import com.reflexio.app.domain.network.MemoryApi
import com.reflexio.app.domain.network.MirrorPortrait
import com.reflexio.app.domain.network.ServerEndpointResolver
import com.reflexio.app.ui.permissions.HealthPermissionGate
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.withContext
import java.time.LocalDate

// ── Same palette ──
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
private val Purple = Color(0xFF8B5CF6)
private val PurpleSoft = Color(0xFFF5F3FF)
private val Rose = Color(0xFFF43F5E)
private val RoseSoft = Color(0xFFFFF1F2)
private val Sky = Color(0xFF0EA5E9)
private val SkySoft = Color(0xFFF0F9FF)

private data class RoleStyle(val title: String, val color: Color, val bg: Color, val icon: ImageVector)

private val roleStyles = mapOf(
    "psychologist" to RoleStyle("Психолог", Purple, PurpleSoft, Icons.Rounded.Psychology),
    "coach" to RoleStyle("Коуч", Mint, MintSoft, Icons.Rounded.SelfImprovement),
    "pattern_detector" to RoleStyle("Паттерны", Indigo, IndigoSoft, Icons.Rounded.TrendingUp),
    "devil_advocate" to RoleStyle("Проверка", Coral, CoralSoft, Icons.Rounded.Psychology),
    "future_predictor" to RoleStyle("Прогноз", Sky, SkySoft, Icons.Rounded.TrendingUp),
)

@OptIn(ExperimentalLayoutApi::class)
@Composable
fun MirrorScreen(
    baseHttpUrl: String,
    onOpenPerson: (String) -> Unit = {},
    onOpenThreads: () -> Unit = {},
    modifier: Modifier = Modifier,
) {
    val context = LocalContext.current
    var portrait by remember { mutableStateOf<MirrorPortrait?>(null) }
    var portraitError by remember { mutableStateOf<String?>(null) }
    var insights by remember { mutableStateOf<List<InsightCard>>(emptyList()) }
    var insightsError by remember { mutableStateOf<String?>(null) }
    var healthMetrics by remember { mutableStateOf<List<CachedHealthMetric>>(emptyList()) }
    var healthGranted by remember { mutableStateOf(false) }

    LaunchedEffect(baseHttpUrl) {
        do {
            portraitError = null
            try {
                portrait = withContext(Dispatchers.IO) { MemoryApi.fetchMirrorPortrait(baseHttpUrl) }
                break
            } catch (e: Exception) {
                portraitError = ServerEndpointResolver.userFacingError(e.message, baseHttpUrl)
                if (!ServerEndpointResolver.isLocalUrl(baseHttpUrl) || !isActive) break
                delay(5_000)
            }
        } while (true)
    }

    LaunchedEffect(baseHttpUrl) {
        do {
            insightsError = null
            try {
                insights = withContext(Dispatchers.IO) { MemoryApi.fetchBalanceInsights(baseHttpUrl, LocalDate.now().toString()) }
                break
            } catch (e: Exception) {
                insightsError = ServerEndpointResolver.userFacingError(e.message, baseHttpUrl)
                if (!ServerEndpointResolver.isLocalUrl(baseHttpUrl) || !isActive) break
                delay(5_000)
            }
        } while (true)
    }

    LaunchedEffect(healthGranted) {
        if (!healthGranted) return@LaunchedEffect
        healthMetrics = withContext(Dispatchers.IO) {
            try {
                val reader = HealthConnectReader(context)
                val db = RecordingDatabase.getInstance(context)
                val lastSync = db.healthMetricDao().lastSyncTime() ?: 0L
                if (System.currentTimeMillis() - lastSync > 15 * 60_000) {
                    val all = reader.readSleep() + reader.readSteps() + reader.readHeartRate()
                    if (all.isNotEmpty()) db.healthMetricDao().insertAll(all)
                }
                db.healthMetricDao().metricsForDate(LocalDate.now().toString())
            } catch (_: Exception) { emptyList() }
        }
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
        Text("Зеркало", fontSize = 32.sp, fontWeight = FontWeight.Black, color = TextPrimary)
        Text(
            "Кто ты сейчас, какие темы тянутся, что повторяется",
            fontSize = 14.sp, color = TextMuted, lineHeight = 18.sp,
        )

        // ── Portrait ──
        when {
            portrait != null -> PortraitSection(portrait!!, onOpenPerson)
            portraitError != null -> ErrorBubble(portraitError!!)
            else -> LoadingCenter()
        }

        // ── Health ──
        HealthPermissionGate(onGranted = { healthGranted = true })
        if (healthMetrics.isNotEmpty()) {
            HealthCard(healthMetrics)
        }

        // ── Insights ──
        if (insights.isNotEmpty() || insightsError != null || portrait == null) {
            Text("Что это говорит о тебе", fontWeight = FontWeight.Bold, fontSize = 18.sp, color = TextPrimary)
        }

        when {
            insights.isNotEmpty() -> {
                insights.forEach { card -> InsightBubble(card) }
            }
            insightsError != null -> ErrorBubble(insightsError!!)
            portrait == null -> LoadingCenter()
            else -> EmptyInsights()
        }

        Spacer(Modifier.height(80.dp))
    }
}

// ── Portrait Section ──

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun PortraitSection(portrait: MirrorPortrait, onOpenPerson: (String) -> Unit) {
    // Stats row
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
        PortraitStat("${portrait.episodesCount}", "Эпизодов", Indigo, IndigoSoft, Modifier.weight(1f))
        PortraitStat(
            portrait.avgSentiment?.let { "${((it + 1f) / 2f * 100).toInt()}%" } ?: "—",
            "Настроение", if ((portrait.avgSentiment ?: 0f) >= 0f) Mint else Coral,
            if ((portrait.avgSentiment ?: 0f) >= 0f) MintSoft else CoralSoft,
            Modifier.weight(1f),
        )
        PortraitStat("${portrait.openCommitments}", "Обещаний", Amber, AmberSoft, Modifier.weight(1f))
    }

    // Emotions
    if (portrait.topEmotions.isNotEmpty()) {
        TagSection("Эмоции", portrait.topEmotions.take(4)) { emotion ->
            val (c, bg) = when {
                emotion.contains("радость") || emotion.contains("энтузиазм") -> Mint to MintSoft
                emotion.contains("тревога") || emotion.contains("раздражение") -> Coral to CoralSoft
                else -> Indigo to IndigoSoft
            }
            Pill(emotion, c, bg)
        }
    }

    // Topics
    if (portrait.topTopics.isNotEmpty()) {
        TagSection("Темы", portrait.topTopics.take(4)) { topic ->
            Pill(topic, Indigo, IndigoSoft)
        }
    }

    // People
    if (portrait.topPeople.isNotEmpty()) {
        TagSection("Люди", portrait.topPeople.take(4)) { person ->
            Surface(
                onClick = { onOpenPerson(person) },
                shape = RoundedCornerShape(12.dp),
                color = PurpleSoft,
            ) {
                Text(person, modifier = Modifier.padding(horizontal = 14.dp, vertical = 7.dp),
                    fontSize = 13.sp, fontWeight = FontWeight.Medium, color = Purple)
            }
        }
    }
}

@Composable
private fun PortraitStat(value: String, label: String, accent: Color, bg: Color, modifier: Modifier) {
    Surface(modifier = modifier, shape = RoundedCornerShape(16.dp), color = bg) {
        Column(Modifier.padding(vertical = 16.dp, horizontal = 8.dp), horizontalAlignment = Alignment.CenterHorizontally) {
            Text(value, fontSize = 22.sp, fontWeight = FontWeight.Black, color = accent)
            Text(label, fontSize = 11.sp, color = accent.copy(alpha = 0.6f), fontWeight = FontWeight.Medium)
        }
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun <T> TagSection(title: String, items: List<T>, content: @Composable (T) -> Unit) {
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Text(title, fontWeight = FontWeight.Bold, fontSize = 15.sp, color = TextPrimary)
        FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            items.forEach { item -> content(item) }
        }
    }
}

// ── Health Card ──

@Composable
private fun HealthCard(metrics: List<CachedHealthMetric>) {
    Surface(shape = RoundedCornerShape(18.dp), color = CardWhite, shadowElevation = 1.dp) {
        Column(Modifier.padding(16.dp)) {
            Text("Здоровье сегодня", fontWeight = FontWeight.Bold, fontSize = 15.sp, color = TextPrimary)
            Spacer(Modifier.height(12.dp))
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceEvenly) {
                metrics.forEach { m ->
                    val (label, display, icon, color) = when (m.metricType) {
                        "sleep_hours" -> HealthDisplay("Сон", "%.1f ч".format(m.value), Icons.Rounded.Hotel, Indigo)
                        "steps" -> HealthDisplay("Шаги", "%,.0f".format(m.value), Icons.Rounded.FitnessCenter, Mint)
                        "heart_rate_avg" -> HealthDisplay("Пульс", "%.0f".format(m.value), Icons.Rounded.Favorite, Coral)
                        else -> HealthDisplay(m.metricType, "%.1f".format(m.value), Icons.Rounded.TrendingUp, Amber)
                    }
                    Column(horizontalAlignment = Alignment.CenterHorizontally) {
                        Box(
                            modifier = Modifier.size(40.dp).clip(RoundedCornerShape(12.dp)).background(color.copy(alpha = 0.1f)),
                            contentAlignment = Alignment.Center,
                        ) { Icon(icon, contentDescription = null, tint = color, modifier = Modifier.size(20.dp)) }
                        Spacer(Modifier.height(6.dp))
                        Text(display, fontWeight = FontWeight.Bold, fontSize = 15.sp, color = TextPrimary)
                        Text(label, fontSize = 11.sp, color = TextMuted)
                    }
                }
            }
        }
    }
}

private data class HealthDisplay(val label: String, val display: String, val icon: ImageVector, val color: Color)

// ── Insight Bubble ──

@Composable
private fun InsightBubble(card: InsightCard) {
    val style = roleStyles[card.role] ?: RoleStyle(
        card.role.replace("_", " ").replaceFirstChar { it.uppercase() },
        Indigo, IndigoSoft, Icons.Rounded.Psychology,
    )

    Surface(shape = RoundedCornerShape(18.dp), color = CardWhite, shadowElevation = 1.dp) {
        Row(Modifier.padding(16.dp), verticalAlignment = Alignment.Top) {
            Box(
                modifier = Modifier.size(40.dp).clip(RoundedCornerShape(12.dp)).background(style.bg),
                contentAlignment = Alignment.Center,
            ) { Icon(style.icon, contentDescription = null, tint = style.color, modifier = Modifier.size(20.dp)) }
            Spacer(Modifier.width(14.dp))
            Column(Modifier.weight(1f)) {
                Text(style.title, fontWeight = FontWeight.Bold, fontSize = 13.sp, color = style.color)
                Spacer(Modifier.height(4.dp))
                Text(card.text, fontSize = 14.sp, color = TextSecondary, lineHeight = 20.sp)
            }
        }
    }
}

// ── Empty / Error / Loading ──

@Composable
private fun EmptyInsights() {
    Surface(shape = RoundedCornerShape(18.dp), color = CardWhite, shadowElevation = 1.dp) {
        Column(Modifier.padding(24.dp).fillMaxWidth(), horizontalAlignment = Alignment.CenterHorizontally) {
            Text("🪞", fontSize = 40.sp)
            Spacer(Modifier.height(8.dp))
            Text("Пока мало интерпретаций", fontWeight = FontWeight.SemiBold, fontSize = 15.sp, color = TextPrimary)
            Spacer(Modifier.height(4.dp))
            Text(
                "Когда накопится больше записей, здесь появятся выводы о тебе",
                fontSize = 13.sp, color = TextMuted, textAlign = TextAlign.Center,
            )
        }
    }
}

@Composable
private fun ErrorBubble(message: String) {
    Surface(shape = RoundedCornerShape(14.dp), color = CoralSoft) {
        Text(message, modifier = Modifier.padding(14.dp), color = Coral, fontSize = 13.sp)
    }
}

@Composable
private fun LoadingCenter() {
    Box(Modifier.fillMaxWidth().height(80.dp), contentAlignment = Alignment.Center) {
        CircularProgressIndicator(color = Indigo, strokeWidth = 3.dp)
    }
}

@Composable
private fun Pill(text: String, accent: Color, bg: Color) {
    Surface(shape = RoundedCornerShape(12.dp), color = bg) {
        Text(text, modifier = Modifier.padding(horizontal = 14.dp, vertical = 7.dp),
            fontSize = 13.sp, fontWeight = FontWeight.Medium, color = accent)
    }
}
