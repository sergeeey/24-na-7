package com.reflexio.app.ui.screens

import android.app.DatePickerDialog
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
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowBack
import androidx.compose.material.icons.filled.ArrowForward
import androidx.compose.material.icons.filled.CalendarMonth
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material3.AssistChip
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
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
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.platform.LocalContext
import com.reflexio.app.domain.network.DailyDigestData
import com.reflexio.app.domain.network.MemoryApi
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.time.LocalDate

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

    LaunchedEffect(baseHttpUrl, selectedDate, retryKey) {
        state = DigestUiState.Loading
        state = try {
            val result = withContext(Dispatchers.IO) {
                MemoryApi.fetchDigest(baseHttpUrl, selectedDate.toString())
            }
            DigestUiState.Success(result)
        } catch (e: Exception) {
            DigestUiState.Error(e.message ?: "Не удалось загрузить дайджест")
        }
    }

    val datePicker = remember {
        DatePickerDialog(
            context,
            { _, year, month, dayOfMonth ->
                selectedDate = LocalDate.of(year, month + 1, dayOfMonth)
            },
            selectedDate.year,
            selectedDate.monthValue - 1,
            selectedDate.dayOfMonth,
        )
    }

    Column(
        modifier = modifier
            .fillMaxSize()
            .padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(14.dp),
    ) {
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Column {
                Text("Daily digest", style = MaterialTheme.typography.labelLarge, color = MaterialTheme.colorScheme.primary)
                Text("Итог дня", style = MaterialTheme.typography.headlineMedium)
            }
            Row {
                IconButton(onClick = { retryKey++ }) {
                    Icon(Icons.Default.Refresh, contentDescription = "Обновить")
                }
            }
        }

        Card(
            modifier = Modifier.fillMaxWidth(),
            shape = androidx.compose.foundation.shape.RoundedCornerShape(22.dp),
            colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface.copy(alpha = 0.86f)),
        ) {
            Column(
                modifier = Modifier.padding(16.dp),
                verticalArrangement = Arrangement.spacedBy(10.dp),
            ) {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    IconButton(onClick = { selectedDate = selectedDate.minusDays(1) }) {
                        Icon(Icons.Default.ArrowBack, contentDescription = "Предыдущий день")
                    }
                    AssistChip(
                        onClick = { datePicker.show() },
                        label = { Text(selectedDate.toString()) },
                        leadingIcon = { Icon(Icons.Default.CalendarMonth, contentDescription = null) },
                    )
                    IconButton(onClick = { selectedDate = selectedDate.plusDays(1) }) {
                        Icon(Icons.Default.ArrowForward, contentDescription = "Следующий день")
                    }
                }
                Text(
                    text = if (selectedDate == LocalDate.now()) {
                        "Текущий дневной срез памяти."
                    } else {
                        "Дайджест за выбранную дату."
                    },
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        }

        when (val current = state) {
            DigestUiState.Loading -> {
                Text("Собираю дайджест...", color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
            is DigestUiState.Error -> {
                Text(current.message, color = MaterialTheme.colorScheme.error)
            }
            is DigestUiState.Success -> {
                DigestBody(current.data)
            }
        }
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun DigestBody(data: DailyDigestData) {
    Column(
        modifier = Modifier.verticalScroll(rememberScrollState()),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        data.notice?.let {
            Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.secondaryContainer)) {
                Text(
                    text = it,
                    modifier = Modifier.padding(12.dp),
                    style = MaterialTheme.typography.bodySmall,
                )
            }
        }

        Card(
            modifier = Modifier.fillMaxWidth(),
            shape = androidx.compose.foundation.shape.RoundedCornerShape(18.dp),
        ) {
            Column(
                modifier = Modifier.padding(16.dp),
                verticalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                Text("Сводка", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold)
                Text(
                    text = data.summaryText.ifBlank { "За этот день пока нет полноценной сводки." },
                    style = MaterialTheme.typography.bodyLarge,
                )
                Text(
                    text = "Записей: ${data.totalRecordings} · Источников: ${data.sourcesCount} · ${data.totalDuration}",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.primary,
                )
            }
        }

        if (data.keyThemes.isNotEmpty()) {
            Text("Темы", style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.Bold)
            FlowRow(
                horizontalArrangement = Arrangement.spacedBy(8.dp),
                verticalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                data.keyThemes.forEach { theme ->
                    AssistChip(onClick = {}, label = { Text(theme) })
                }
            }
        }

        if (data.emotions.isNotEmpty()) {
            Text("Эмоции", style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.Bold)
            FlowRow(
                horizontalArrangement = Arrangement.spacedBy(8.dp),
                verticalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                data.emotions.forEach { emotion ->
                    AssistChip(onClick = {}, label = { Text(emotion) })
                }
            }
        }

        if (data.actions.isNotEmpty()) {
            Text("Намерения", style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.Bold)
            data.actions.forEach { action ->
                Card(
                    modifier = Modifier.fillMaxWidth(),
                    shape = androidx.compose.foundation.shape.RoundedCornerShape(16.dp),
                    colors = CardDefaults.cardColors(
                        containerColor = MaterialTheme.colorScheme.surface.copy(alpha = 0.86f),
                    ),
                ) {
                    Column(
                        modifier = Modifier.padding(14.dp),
                        verticalArrangement = Arrangement.spacedBy(4.dp),
                    ) {
                        Text(action.text, style = MaterialTheme.typography.bodyMedium)
                        Text(
                            text = "Статус: ${if (action.done) "сделано" else "в работе"} · приоритет: ${action.urgency}",
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }
                }
            }
        }

        Spacer(modifier = Modifier.height(16.dp))
    }
}
