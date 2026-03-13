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
import com.reflexio.app.domain.network.ServerEndpointResolver
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.time.LocalDate

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

    LaunchedEffect(baseHttpUrl) {
        portraitError = null
        try {
            portrait = withContext(Dispatchers.IO) { MemoryApi.fetchMirrorPortrait(baseHttpUrl) }
        } catch (e: Exception) {
            portraitError = ServerEndpointResolver.userFacingError(e.message, baseHttpUrl)
        }
    }

    LaunchedEffect(baseHttpUrl) {
        insightsError = null
        try {
            val today = LocalDate.now().toString()
            insights = withContext(Dispatchers.IO) { MemoryApi.fetchBalanceInsights(baseHttpUrl, today) }
        } catch (e: Exception) {
            insightsError = ServerEndpointResolver.userFacingError(e.message, baseHttpUrl)
        }
    }

    Column(
        modifier = modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(horizontal = 16.dp, vertical = 12.dp),
    ) {
        Text(
            text = "Зеркало",
            style = MaterialTheme.typography.headlineSmall,
            fontWeight = FontWeight.Bold,
        )
        Spacer(Modifier.height(4.dp))
        Text(
            text = "Не хроника дня, а короткая интерпретация: кто ты сейчас, какие темы повторяются и что тянется фоном.",
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
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

        Text(
            text = "Что это говорит о тебе",
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
            portrait == null -> LoadingRow()
            else -> CompactEmptyMirrorState()
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
                text = "Срез последних дней",
                style = MaterialTheme.typography.titleSmall,
                color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.6f),
            )
            Spacer(Modifier.height(12.dp))

            Row(horizontalArrangement = Arrangement.spacedBy(24.dp)) {
                StatItem(label = "Эпизодов", value = portrait.episodesCount.toString())
                StatItem(
                    label = "Настроение",
                    value = portrait.avgSentiment?.let { "${((it + 1f) / 2f * 100).toInt()}%" } ?: "—",
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
    val roleTitle = when (card.role) {
        "psychologist" -> "Психолог"
        "coach" -> "Коуч"
        "pattern_detector" -> "Паттерны"
        "devil_advocate" -> "Проверка на самообман"
        "future_predictor" -> "Прогноз"
        else -> card.role.replace("_", " ").replaceFirstChar { it.uppercase() }
    }

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
                text = roleTitle,
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

@Composable
private fun CompactEmptyMirrorState() {
    Card(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(18.dp),
        colors = CardDefaults.cardColors(
            containerColor = MaterialTheme.colorScheme.surface.copy(alpha = 0.88f),
        ),
    ) {
        Column(
            modifier = Modifier.padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(6.dp),
        ) {
            Text("Пока мало интерпретаций", fontWeight = FontWeight.SemiBold)
            Text(
                "Когда накопится больше осмысленных записей, здесь появятся повторяющиеся линии и короткие выводы о тебе.",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
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

