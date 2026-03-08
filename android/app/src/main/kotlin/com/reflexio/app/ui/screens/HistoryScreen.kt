package com.reflexio.app.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.reflexio.app.data.db.RecordingDatabase
import com.reflexio.app.data.model.Recording

private val HistoryIndigo = Color(0xFF7C6CFF)
private val HistoryTeal = Color(0xFF00E5CC)
private val HistoryAmber = Color(0xFFFFB74D)

@Composable
fun HistoryScreen(
    database: RecordingDatabase,
    modifier: Modifier = Modifier,
) {
    val recordings by remember(database) { database.recordingDao().getAllRecordings() }
        .collectAsState(initial = emptyList())

    val processedCount = recordings.count { it.status == "processed" }
    val pendingCount = recordings.count { it.status == "pending_upload" || it.status == "uploaded" }
    val totalMinutes = recordings.sumOf { it.durationSeconds }.div(60)

    Column(
        modifier = modifier
            .fillMaxSize()
            .padding(horizontal = 16.dp, vertical = 8.dp),
        verticalArrangement = Arrangement.spacedBy(14.dp),
    ) {
        HistoryHeroCard(recordings = recordings)

        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            HistoryMetricCard(
                label = "Всего",
                value = recordings.size.toString(),
                accent = HistoryTeal,
                modifier = Modifier.weight(1f),
            )
            HistoryMetricCard(
                label = "Обработано",
                value = processedCount.toString(),
                accent = HistoryIndigo,
                modifier = Modifier.weight(1f),
            )
            HistoryMetricCard(
                label = "Минут",
                value = totalMinutes.toString(),
                accent = HistoryAmber,
                modifier = Modifier.weight(1f),
            )
        }

        if (pendingCount > 0) {
            Card(
                modifier = Modifier.fillMaxWidth(),
                colors = CardDefaults.cardColors(
                    containerColor = HistoryAmber.copy(alpha = 0.12f),
                ),
                shape = RoundedCornerShape(18.dp),
            ) {
                Text(
                    text = "В очереди ещё $pendingCount записей. Они появятся в истории после обработки.",
                    style = MaterialTheme.typography.bodySmall,
                    color = HistoryAmber,
                    modifier = Modifier.padding(12.dp),
                )
            }
        }

        RecordingListScreen(
            recordings = recordings,
            modifier = Modifier.weight(1f, fill = true),
        )
    }
}

@Composable
private fun HistoryHeroCard(recordings: List<Recording>) {
    val latest = recordings.firstOrNull()
    Card(
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(
            containerColor = MaterialTheme.colorScheme.surface.copy(alpha = 0.82f),
        ),
        shape = RoundedCornerShape(26.dp),
    ) {
        Column(
            modifier = Modifier
                .background(
                    brush = Brush.linearGradient(
                        colors = listOf(
                            HistoryIndigo.copy(alpha = 0.22f),
                            HistoryTeal.copy(alpha = 0.08f),
                        ),
                    ),
                )
                .padding(18.dp),
            verticalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            Text(
                text = "Living memory",
                style = MaterialTheme.typography.labelLarge,
                color = HistoryTeal,
            )
            Text(
                text = "История сохраняет живую ленту ваших фрагментов дня: что было сказано, что уже обработано и какие темы начинают повторяться.",
                style = MaterialTheme.typography.bodyLarge,
                color = MaterialTheme.colorScheme.onSurface,
            )
            latest?.let { rec ->
                val preview = rec.summary?.takeIf { it.isNotBlank() }
                    ?: rec.transcription?.takeIf { it.isNotBlank() }
                    ?: "Последняя запись пока без текста."
                Text(
                    text = preview,
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    maxLines = 2,
                    overflow = TextOverflow.Ellipsis,
                )
            }
        }
    }
}

@Composable
private fun HistoryMetricCard(
    label: String,
    value: String,
    accent: Color,
    modifier: Modifier = Modifier,
) {
    Card(
        modifier = modifier,
        colors = CardDefaults.cardColors(
            containerColor = MaterialTheme.colorScheme.surface.copy(alpha = 0.78f),
        ),
        shape = RoundedCornerShape(18.dp),
    ) {
        Column(
            modifier = Modifier.padding(12.dp),
            verticalArrangement = Arrangement.spacedBy(4.dp),
        ) {
            Text(
                text = label,
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            Text(
                text = value,
                style = MaterialTheme.typography.titleLarge,
                color = accent,
                fontWeight = FontWeight.Bold,
            )
        }
    }
}
