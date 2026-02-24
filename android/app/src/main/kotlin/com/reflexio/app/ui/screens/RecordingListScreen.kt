package com.reflexio.app.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.IntrinsicSize
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.Checklist
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.reflexio.app.data.model.Recording
import com.reflexio.app.data.model.RecordingStatus
import com.reflexio.app.ui.components.EmptyState

private val StatusColorProcessed = Color(0xFF00E5CC)
private val StatusColorPending = Color(0xFFFFB74D)
private val StatusColorFailed = Color(0xFFFF6B6B)
private val StatusColorDefault = Color(0xFF9E9E9E)

internal fun formatRelativeTime(timestamp: Long): String {
    val nowMs = System.currentTimeMillis()
    val diffMs = nowMs - timestamp
    val oneMinuteMs = 60_000L
    val oneHourMs = 60 * oneMinuteMs
    val oneDayMs = 24 * oneHourMs
    val twoDaysMs = 2 * oneDayMs

    return when {
        diffMs < oneMinuteMs -> "только что"
        diffMs < oneHourMs -> {
            val minutes = (diffMs / oneMinuteMs).toInt()
            "$minutes мин назад"
        }
        diffMs < oneDayMs -> {
            val hours = (diffMs / oneHourMs).toInt()
            "$hours ч назад"
        }
        diffMs < twoDaysMs -> "Вчера"
        else -> {
            val days = (diffMs / oneDayMs).toInt()
            "$days дн назад"
        }
    }
}

private fun statusColor(status: String): Color = when (status) {
    RecordingStatus.PROCESSED -> StatusColorProcessed
    RecordingStatus.PENDING_UPLOAD -> StatusColorPending
    RecordingStatus.FAILED -> StatusColorFailed
    else -> StatusColorDefault
}

// ПОЧЕМУ: текстовый статус даёт больше информации чем цветная точка —
// пользователь не должен запоминать что значит каждый цвет
private fun statusLabel(status: String): String = when (status) {
    RecordingStatus.PROCESSED -> "Готово"
    RecordingStatus.PENDING_UPLOAD -> "Отправка"
    RecordingStatus.FAILED -> "Ошибка"
    else -> "Загружено"
}

// ПОЧЕМУ: извлекаем заголовок из транскрипции пока нет LLM-summary от сервера.
// Берём первые 6 слов — это обычно достаточно чтобы понять о чём запись.
// Когда появится поле Recording.summary — заменим на него.
private fun extractTitle(transcription: String?): String? {
    if (transcription.isNullOrBlank()) return null
    val words = transcription.trim().split("\\s+".toRegex())
    val title = words.take(6).joinToString(" ")
    return if (words.size > 6) "$title…" else title
}

@Composable
fun RecordingListScreen(
    recordings: List<Recording>,
    onRecordingClick: (Recording) -> Unit = {},
    modifier: Modifier = Modifier
) {
    if (recordings.isEmpty()) {
        EmptyState(modifier = modifier)
        return
    }
    LazyColumn(
        modifier = modifier,
        verticalArrangement = Arrangement.spacedBy(10.dp)
    ) {
        items(recordings) { recording ->
            RecordingItem(
                recording = recording,
                onClick = { onRecordingClick(recording) },
            )
        }
    }
}

@Composable
private fun RecordingItem(
    recording: Recording,
    onClick: () -> Unit = {},
    modifier: Modifier = Modifier
) {
    val relativeTime = formatRelativeTime(recording.createdAt)
    val title = extractTitle(recording.transcription)
    val statusText = statusLabel(recording.status)
    val statusBgColor = statusColor(recording.status)
    val accentColor = MaterialTheme.colorScheme.secondary
    val surfaceColor = MaterialTheme.colorScheme.surfaceVariant
    val cardShape = MaterialTheme.shapes.medium

    Row(
        modifier = modifier
            .fillMaxWidth()
            .padding(horizontal = 16.dp)
            .clip(cardShape)
            .background(surfaceColor)
            .clickable(onClick = onClick)
            .height(IntrinsicSize.Min)
    ) {
        // Левая акцентная полоса
        Box(
            modifier = Modifier
                .width(4.dp)
                .fillMaxHeight()
                .background(accentColor)
        )

        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 12.dp, vertical = 10.dp)
        ) {
            // Строка 1: Заголовок (или "Запись") + время
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically,
            ) {
                // ПОЧЕМУ: заголовок из первых слов транскрипции делает карточку
                // "умной" — пользователь видит о чём запись не открывая её.
                // Когда подключим LLM-summary — просто заменим extractTitle().
                Text(
                    text = title ?: "Новая запись",
                    style = MaterialTheme.typography.titleSmall.copy(
                        fontWeight = FontWeight.SemiBold,
                    ),
                    color = MaterialTheme.colorScheme.onSurface,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                    modifier = Modifier.weight(1f),
                )
                Spacer(modifier = Modifier.width(8.dp))
                Text(
                    text = relativeTime,
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }

            Spacer(modifier = Modifier.height(4.dp))

            // Строка 2: Транскрипция (полная, до 2 строк)
            recording.transcription?.takeIf { it.isNotBlank() }?.let { text ->
                Text(
                    text = text,
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    maxLines = 2,
                    overflow = TextOverflow.Ellipsis,
                )
                Spacer(modifier = Modifier.height(8.dp))
            }

            // Строка 3: Статус-бейдж + будущие теги
            // ПОЧЕМУ Row а не FlowRow: пока у нас только 1 бейдж (статус).
            // Когда подключим topics/emotions из API — заменим на FlowRow + chips.
            Row(
                horizontalArrangement = Arrangement.spacedBy(6.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                // Статус-бейдж
                StatusBadge(text = statusText, color = statusBgColor)

                // Иконка задачи — если в транскрипции есть слова-маркеры
                // ПОЧЕМУ: простая эвристика пока нет LLM-анализа задач.
                // Ищем "надо", "нужно", "задача", "сделать" — типичные маркеры задач в речи.
                if (recording.transcription?.let { hasTaskMarkers(it) } == true) {
                    Icon(
                        imageVector = Icons.Outlined.Checklist,
                        contentDescription = "Содержит задачу",
                        modifier = Modifier.size(16.dp),
                        tint = StatusColorPending,
                    )
                }
            }
        }
    }
}

// ПОЧЕМУ Surface а не Box+background: Surface из Material3 уже имеет встроенные
// настройки для tonalElevation, shape и contentColor. Для badge это overkill,
// но зато единообразно с остальными Material3 компонентами.
@Composable
private fun StatusBadge(text: String, color: Color) {
    Surface(
        color = color.copy(alpha = 0.15f),
        contentColor = color,
        shape = RoundedCornerShape(4.dp),
    ) {
        Text(
            text = text,
            style = MaterialTheme.typography.labelSmall,
            modifier = Modifier.padding(horizontal = 8.dp, vertical = 2.dp),
        )
    }
}

// Простая эвристика для определения задач в тексте.
// TODO: заменить на анализ поля Recording.tasks когда появится enrichment API.
private fun hasTaskMarkers(text: String): Boolean {
    val markers = listOf("надо", "нужно", "задача", "сделать", "todo", "напомни")
    val lower = text.lowercase()
    return markers.any { it in lower }
}
