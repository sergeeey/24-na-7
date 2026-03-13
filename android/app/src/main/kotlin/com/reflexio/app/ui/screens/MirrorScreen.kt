package com.reflexio.app.ui.screens

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AssistChip
import androidx.compose.material3.AssistChipDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.reflexio.app.domain.network.InsightCard
import com.reflexio.app.domain.network.MemoryApi
import com.reflexio.app.domain.network.MirrorPortrait
import com.reflexio.app.domain.network.ThreadSummary
import com.reflexio.app.ui.components.BalanceWheelVisualizer
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.time.LocalDate

// ПОЧЕМУ: DensityInfo — локальная модель экрана, не нужна в общем network-слое
private data class DensityInfo(
    val percentage: Float,
    val verdict: String?,
)

// ПОЧЕМУ: цвета ролей вынесены в константу — они семантически фиксированы
// и не должны меняться вместе с темой
private val roleColors = mapOf(
    "psychologist" to Color(0xFFE040FB),
    "coach" to Color(0xFF42E5C2),
    "pattern_detector" to Color(0xFF7C6CFF),
    "devil_advocate" to Color(0xFFFF6B6B),
    "future_predictor" to Color(0xFF29B6F6),
)

@OptIn(ExperimentalLayoutApi::class)
@Composable
fun MirrorScreen(
    baseHttpUrl: String,
    onOpenPerson: (String) -> Unit = {},
    onOpenThreads: () -> Unit = {},
    modifier: Modifier = Modifier,
) {
    // ПОЧЕМУ: три независимых LaunchedEffect — секции грузятся параллельно
    // и не блокируют друг друга при частичной недоступности API
    var portrait by remember { mutableStateOf<MirrorPortrait?>(null) }
    var portraitError by remember { mutableStateOf<String?>(null) }

    var insights by remember { mutableStateOf<List<InsightCard>>(emptyList()) }
    var insightsError by remember { mutableStateOf<String?>(null) }

    var threads by remember { mutableStateOf<List<ThreadSummary>>(emptyList()) }
    var threadsError by remember { mutableStateOf<String?>(null) }

    var density by remember { mutableStateOf<DensityInfo?>(null) }

    LaunchedEffect(baseHttpUrl) {
        try {
            density = withContext(Dispatchers.IO) {
                fetchDensity(baseHttpUrl)
            }
        } catch (_: Exception) {
            density = null
        }
    }

    LaunchedEffect(baseHttpUrl) {
        portraitError = null
        try {
            portrait = withContext(Dispatchers.IO) { MemoryApi.fetchMirrorPortrait(baseHttpUrl) }
        } catch (e: Exception) {
            portraitError = e.message
        }
    }

    LaunchedEffect(baseHttpUrl) {
        insightsError = null
        try {
            val today = LocalDate.now().toString()
            insights = withContext(Dispatchers.IO) { MemoryApi.fetchBalanceInsights(baseHttpUrl, today) }
        } catch (e: Exception) {
            insightsError = e.message
        }
    }

    LaunchedEffect(baseHttpUrl) {
        threadsError = null
        try {
            threads = withContext(Dispatchers.IO) {
                MemoryApi.queryThreads(baseHttpUrl, daysBack = 30)
            }.take(5)
        } catch (e: Exception) {
            threadsError = e.message
        }
    }

    Column(
        modifier = modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(horizontal = 16.dp, vertical = 12.dp),
    ) {
        // Зеркало дня
        density?.let { d ->
            Card(
                modifier = Modifier.fillMaxWidth(),
                shape = RoundedCornerShape(20.dp),
                colors = CardDefaults.cardColors(
                    containerColor = MaterialTheme.colorScheme.primaryContainer.copy(alpha = 0.3f),
                ),
            ) {
                Column(
                    modifier = Modifier.padding(16.dp),
                    verticalArrangement = Arrangement.spacedBy(8.dp),
                ) {
                    Text(
                        "Зеркало дня",
                        style = MaterialTheme.typography.titleMedium,
                        fontWeight = FontWeight.Bold,
                    )
                    Text(
                        "Память дня заполнена на ${"%.0f".format(d.percentage)}%",
                        style = MaterialTheme.typography.bodyLarge,
                    )
                    d.verdict?.let { v ->
                        Text(
                            v,
                            style = MaterialTheme.typography.bodyMedium,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }
                }
            }
            Spacer(Modifier.height(16.dp))
        }

        // ── Section 1: Portrait ──────────────────────────────────────────────
        Text(
            text = "Зеркало",
            style = MaterialTheme.typography.headlineSmall,
            fontWeight = FontWeight.Bold,
        )
        Spacer(Modifier.height(12.dp))

        when {
            portrait != null -> PortraitCard(
                portrait = portrait!!,
                onOpenPerson = onOpenPerson,
            )
            portraitError != null -> ErrorText(portraitError!!)
            else -> LoadingRow()
        }

        Spacer(Modifier.height(16.dp))

        // ── Section 2: Balance Wheel ─────────────────────────────────────────
        Text(
            text = "Колесо баланса",
            style = MaterialTheme.typography.titleMedium,
            fontWeight = FontWeight.Bold,
        )
        Spacer(Modifier.height(8.dp))

        BalanceWheelVisualizer(
            baseHttpUrl = baseHttpUrl,
            showCenterControl = false,
            modifier = Modifier
                .fillMaxWidth()
                .height(300.dp),
        )

        Spacer(Modifier.height(16.dp))

        // ── Section 3: Insights ──────────────────────────────────────────────
        Text(
            text = "Инсайты дня",
            style = MaterialTheme.typography.titleMedium,
            fontWeight = FontWeight.Bold,
        )
        Spacer(Modifier.height(8.dp))

        when {
            insights.isNotEmpty() -> insights.forEach { card ->
                InsightRow(card = card)
                Spacer(Modifier.height(6.dp))
            }
            insightsError != null -> ErrorText(insightsError!!)
            else -> LoadingRow()
        }

        Spacer(Modifier.height(16.dp))

        // ── Section 4: Threads ───────────────────────────────────────────────
        Row(
            modifier = Modifier.fillMaxWidth(),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.SpaceBetween,
        ) {
            Text(
                text = "Потоки",
                style = MaterialTheme.typography.titleMedium,
                fontWeight = FontWeight.Bold,
            )
            TextButton(onClick = onOpenThreads) {
                Text("Показать все")
            }
        }
        Spacer(Modifier.height(8.dp))

        when {
            threads.isNotEmpty() -> threads.forEach { thread ->
                ThreadRow(thread = thread)
                Spacer(Modifier.height(6.dp))
            }
            threadsError != null -> ErrorText(threadsError!!)
            else -> LoadingRow()
        }

        Spacer(Modifier.height(24.dp))
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun PortraitCard(
    portrait: MirrorPortrait,
    onOpenPerson: (String) -> Unit,
) {
    Card(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(20.dp),
        // ПОЧЕМУ: alpha 0.88 даёт лёгкую прозрачность, сохраняя читаемость
        // и визуально отделяя карточку от фона без жёсткой границы
        colors = CardDefaults.cardColors(
            containerColor = MaterialTheme.colorScheme.surface.copy(alpha = 0.88f),
        ),
        elevation = CardDefaults.cardElevation(defaultElevation = 4.dp),
    ) {
        Column(modifier = Modifier.padding(20.dp)) {
            Text(
                text = "Вот кто ты за последнюю неделю",
                style = MaterialTheme.typography.titleSmall,
                color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.6f),
            )
            Spacer(Modifier.height(12.dp))

            Row(horizontalArrangement = Arrangement.spacedBy(24.dp)) {
                StatItem(label = "Эпизодов", value = portrait.episodesCount.toString())
                StatItem(
                    label = "Настроение",
                    value = "${((portrait.avgSentiment + 1f) / 2f * 100).toInt()}%",
                )
                StatItem(label = "Обязательств", value = portrait.openCommitments.toString())
            }

            if (portrait.topEmotions.isNotEmpty()) {
                Spacer(Modifier.height(12.dp))
                Text(
                    text = "Эмоции",
                    style = MaterialTheme.typography.labelMedium,
                    color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.55f),
                )
                Spacer(Modifier.height(4.dp))
                FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    portrait.topEmotions.take(3).forEach { emotion ->
                        AssistChip(onClick = {}, label = { Text(emotion) })
                    }
                }
            }

            if (portrait.topTopics.isNotEmpty()) {
                Spacer(Modifier.height(8.dp))
                Text(
                    text = "Темы",
                    style = MaterialTheme.typography.labelMedium,
                    color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.55f),
                )
                Spacer(Modifier.height(4.dp))
                FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    portrait.topTopics.take(3).forEach { topic ->
                        AssistChip(onClick = {}, label = { Text(topic) })
                    }
                }
            }

            if (portrait.topPeople.isNotEmpty()) {
                Spacer(Modifier.height(8.dp))
                Text(
                    text = "Люди",
                    style = MaterialTheme.typography.labelMedium,
                    color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.55f),
                )
                Spacer(Modifier.height(4.dp))
                FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    portrait.topPeople.take(3).forEach { person ->
                        // ПОЧЕМУ: кликабельность вынесена на chips людей,
                        // а не на всю карточку — точечное действие удобнее
                        AssistChip(
                            onClick = { onOpenPerson(person) },
                            label = { Text(person) },
                            colors = AssistChipDefaults.assistChipColors(
                                containerColor = MaterialTheme.colorScheme.secondaryContainer,
                            ),
                        )
                    }
                }
            }
        }
    }
}

@Composable
private fun StatItem(label: String, value: String) {
    Column(horizontalAlignment = Alignment.CenterHorizontally) {
        Text(
            text = value,
            style = MaterialTheme.typography.titleLarge,
            fontWeight = FontWeight.Bold,
        )
        Text(
            text = label,
            style = MaterialTheme.typography.labelSmall,
            color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.55f),
        )
    }
}

@Composable
private fun InsightRow(card: InsightCard) {
    val accentColor = roleColors[card.role] ?: MaterialTheme.colorScheme.primary

    Card(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(18.dp),
        colors = CardDefaults.cardColors(
            containerColor = MaterialTheme.colorScheme.surface.copy(alpha = 0.88f),
        ),
        elevation = CardDefaults.cardElevation(defaultElevation = 2.dp),
    ) {
        Column(modifier = Modifier.padding(14.dp)) {
            Text(
                text = card.role.replace("_", " ").replaceFirstChar { it.uppercase() },
                style = MaterialTheme.typography.labelMedium,
                fontWeight = FontWeight.Bold,
                color = accentColor,
            )
            Spacer(Modifier.height(4.dp))
            Text(
                text = card.text,
                style = MaterialTheme.typography.bodyMedium,
            )
        }
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun ThreadRow(thread: ThreadSummary) {
    Card(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(18.dp),
        colors = CardDefaults.cardColors(
            containerColor = MaterialTheme.colorScheme.surface.copy(alpha = 0.88f),
        ),
        elevation = CardDefaults.cardElevation(defaultElevation = 2.dp),
    ) {
        Column(modifier = Modifier.padding(14.dp)) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.Top,
            ) {
                Text(
                    text = thread.summary.ifBlank { thread.latestSummary },
                    style = MaterialTheme.typography.bodyMedium,
                    modifier = Modifier.weight(1f),
                )
                Text(
                    text = "${(thread.continuityScore * 100).toInt()}%",
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.5f),
                    modifier = Modifier.padding(start = 8.dp),
                )
            }

            if (thread.participants.isNotEmpty()) {
                Spacer(Modifier.height(6.dp))
                FlowRow(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                    thread.participants.forEach { participant ->
                        AssistChip(
                            onClick = {},
                            label = { Text(participant, style = MaterialTheme.typography.labelSmall) },
                        )
                    }
                }
            }
        }
    }
}

@Composable
private fun LoadingRow() {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .padding(vertical = 12.dp),
        horizontalArrangement = Arrangement.Center,
    ) {
        CircularProgressIndicator()
    }
}

@Composable
private fun ErrorText(message: String) {
    Text(
        text = message,
        style = MaterialTheme.typography.bodySmall,
        color = MaterialTheme.colorScheme.error,
        modifier = Modifier.padding(vertical = 4.dp),
    )
}

// ПОЧЕМУ: fetchDensity вынесен как top-level private fun (не suspend) —
// вызывается внутри withContext(Dispatchers.IO), OkHttp синхронный по дизайну
private fun fetchDensity(baseHttpUrl: String): DensityInfo {
    val today = java.time.LocalDate.now().toString()
    val request = okhttp3.Request.Builder()
        .url("${baseHttpUrl.removeSuffix("/")}/digest/$today/density")
        .apply {
            if (com.reflexio.app.BuildConfig.SERVER_API_KEY.isNotEmpty()) {
                addHeader("Authorization", "Bearer ${com.reflexio.app.BuildConfig.SERVER_API_KEY}")
            }
        }
        .get()
        .build()
    com.reflexio.app.domain.network.NetworkClients.sharedClient.newCall(request).execute().use { resp ->
        if (!resp.isSuccessful) return DensityInfo(0f, null)
        val body = resp.body?.string() ?: return DensityInfo(0f, null)
        val json = org.json.JSONObject(body)
        return DensityInfo(
            percentage = json.optDouble("density_percentage", 0.0).toFloat(),
            verdict = json.optString("verdict").ifBlank {
                json.optString("summary_text").ifBlank { null }
            },
        )
    }
}
