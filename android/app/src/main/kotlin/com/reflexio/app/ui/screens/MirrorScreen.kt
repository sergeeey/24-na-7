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
import com.reflexio.app.domain.network.CountedItem
import com.reflexio.app.domain.network.MirrorPortrait
import com.reflexio.app.domain.network.ServerEndpointResolver
import com.reflexio.app.ui.permissions.HealthPermissionGate
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.withContext
import java.time.LocalDate

// ── Design System: Dark Glassmorphism ──
private val PageBg = Color.Transparent
private val CardWhite = Color(0x1AFFFFFF) // 10% white for glass effect
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
private val Purple = Color(0xFFC084FC)
private val PurpleSoft = Color(0x26C084FC)
private val Rose = Color(0xFFFB7185)
private val RoseSoft = Color(0x26FB7185)
private val Sky = Color(0xFF38BDF8)
private val SkySoft = Color(0x2638BDF8)

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
            "Кто ты сейчас, что на тебя влияет, что повторяется",
            fontSize = 14.sp, color = TextMuted, lineHeight = 18.sp,
        )

        when {
            portrait != null -> {
                val p = portrait!!

                // ── Section 1: Кто я сейчас (Identity) ──
                SectionHeader("Кто я сейчас")
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                    PortraitStat("${p.episodesCount}", "Эпизодов", Indigo, IndigoSoft, Modifier.weight(1f))
                    PortraitStat(
                        p.avgSentiment?.let { "${((it + 1f) / 2f * 100).toInt()}%" } ?: "—",
                        "Настроение", if ((p.avgSentiment ?: 0f) >= 0f) Mint else Coral,
                        if ((p.avgSentiment ?: 0f) >= 0f) MintSoft else CoralSoft,
                        Modifier.weight(1f),
                    )
                    PortraitStat("${p.openCommitments}", "Обещаний", Amber, AmberSoft, Modifier.weight(1f))
                }
                if (p.topEmotions.isNotEmpty()) {
                    TagSection("Эмоции", p.topEmotions.take(4)) { item ->
                        val label = if (item.count > 0) "${item.name} (${item.count})" else item.name
                        val (c, bg) = when {
                            item.name.contains("радость") || item.name.contains("энтузиазм") -> Mint to MintSoft
                            item.name.contains("тревога") || item.name.contains("раздражение") -> Coral to CoralSoft
                            else -> Indigo to IndigoSoft
                        }
                        Pill(label, c, bg)
                    }
                }
                if (p.topTopics.isNotEmpty()) {
                    TagSection("Темы", p.topTopics.take(4)) { item ->
                        val label = if (item.count > 0) "${item.name} (${item.count})" else item.name
                        Pill(label, Indigo, IndigoSoft)
                    }
                }

                // ── Section 2: Что на меня влияет (Influences) ──
                if (p.topPeople.isNotEmpty() || p.balanceTrend.isNotEmpty()) {
                    SectionHeader("Что на меня влияет")
                    if (p.topPeople.isNotEmpty()) {
                        TagSection("Люди", p.topPeople.take(4)) { item ->
                            val label = if (item.count > 0) "${item.name} (${item.count})" else item.name
                            Surface(
                                onClick = { onOpenPerson(item.name) },
                                shape = RoundedCornerShape(12.dp),
                                color = PurpleSoft,
                            ) {
                                Text(label, modifier = Modifier.padding(horizontal = 14.dp, vertical = 7.dp),
                                    fontSize = 13.sp, fontWeight = FontWeight.Medium, color = Purple)
                            }
                        }
                    }
                    if (p.balanceTrend.isNotEmpty()) {
                        Surface(shape = RoundedCornerShape(18.dp), color = CardWhite, shadowElevation = 1.dp) {
                            Column(Modifier.padding(16.dp)) {
                                Text("Баланс жизни", fontWeight = FontWeight.Bold, fontSize = 15.sp, color = TextPrimary)
                                Spacer(Modifier.height(10.dp))
                                p.balanceTrend.sortedByDescending { it.avgScore }.forEach { bd ->
                                    val pct = (bd.avgScore * 100).toInt()
                                    val color = if (pct >= 50) Mint else Amber
                                    Row(Modifier.fillMaxWidth().padding(vertical = 3.dp), verticalAlignment = Alignment.CenterVertically) {
                                        Text(bd.domain, fontSize = 13.sp, color = TextSecondary, modifier = Modifier.width(90.dp))
                                        Box(
                                            Modifier.weight(1f).height(8.dp)
                                                .clip(RoundedCornerShape(4.dp))
                                                .background(color.copy(alpha = 0.15f))
                                        ) {
                                            Box(
                                                Modifier.fillMaxWidth(bd.avgScore.coerceIn(0f, 1f)).height(8.dp)
                                                    .clip(RoundedCornerShape(4.dp))
                                                    .background(color)
                                            )
                                        }
                                        Text("$pct%", fontSize = 12.sp, color = TextMuted,
                                            modifier = Modifier.width(40.dp), textAlign = TextAlign.End)
                                    }
                                }
                            }
                        }
                    }
                }

                // ── Section 3: Что повторяется (Patterns) ──
                if (p.openCommitments > 0) {
                    SectionHeader("Что повторяется")
                    Surface(shape = RoundedCornerShape(14.dp), color = AmberSoft) {
                        Text("${p.openCommitments} открытых обещаний", modifier = Modifier.padding(14.dp),
                            color = Amber, fontSize = 14.sp, fontWeight = FontWeight.Medium)
                    }
                }

                // ── Section 4: Health ──
                HealthPermissionGate(onGranted = { healthGranted = true })
                if (healthMetrics.isNotEmpty()) {
                    HealthCard(healthMetrics)
                }

                // ── Section 5: Почему система так думает (Evidence) ──
                p.dataQuality?.let { dq ->
                    SectionHeader("На чём основано")
                    Surface(shape = RoundedCornerShape(18.dp), color = CardWhite, shadowElevation = 1.dp) {
                        Column(Modifier.padding(16.dp)) {
                            val trustPct = (dq.trustedFraction * 100).toInt()
                            val trustColor = if (trustPct >= 30) Mint else Coral
                            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                                Text("Доверие", fontSize = 13.sp, color = TextSecondary)
                                Text("$trustPct% (${dq.trustedCount}/${dq.totalEvents})",
                                    fontSize = 13.sp, fontWeight = FontWeight.Bold, color = trustColor)
                            }
                            Spacer(Modifier.height(8.dp))
                            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                                Text("Мой голос", fontSize = 13.sp, color = TextSecondary)
                                Text("${p.ownershipSelf}", fontSize = 13.sp, fontWeight = FontWeight.Bold, color = Mint)
                            }
                            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                                Text("Чужой / фон", fontSize = 13.sp, color = TextSecondary)
                                Text("${p.ownershipOther}", fontSize = 13.sp, fontWeight = FontWeight.Bold, color = TextMuted)
                            }
                        }
                    }
                }

                // ── Insights ──
                if (insights.isNotEmpty()) {
                    SectionHeader("Что это говорит о тебе")
                    insights.forEach { card -> InsightBubble(card) }
                } else if (insightsError != null) {
                    ErrorBubble(insightsError!!)
                }
            }
            portraitError != null -> ErrorBubble(portraitError!!)
            else -> LoadingCenter()
        }

        Spacer(Modifier.height(80.dp))
    }
}

// ── Section Header ──

@Composable
private fun SectionHeader(title: String) {
    Spacer(Modifier.height(8.dp))
    Text(title, fontWeight = FontWeight.Bold, fontSize = 18.sp, color = TextPrimary)
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
