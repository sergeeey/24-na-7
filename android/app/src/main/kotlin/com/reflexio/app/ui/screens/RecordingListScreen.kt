package com.reflexio.app.ui.screens

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.IntrinsicSize
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.reflexio.app.data.model.Recording
import com.reflexio.app.data.model.RecordingStatus
import com.reflexio.app.ui.components.EmptyState

// ПОЧЕМУ: Цвета статусов определены как константы верхнего уровня файла — они не зависят
// от Compose-контекста (не нужен @Composable), и их можно переиспользовать в превью и тестах.
private val StatusColorProcessed = Color(0xFF00E5CC)
private val StatusColorPending = Color(0xFFFFB74D)
private val StatusColorFailed = Color(0xFFFF6B6B)
private val StatusColorDefault = Color(0xFF9E9E9E) // серый для UPLOADED и неизвестных

/**
 * Форматирует Unix-timestamp (мс) в человекочитаемое относительное время на русском языке.
 *
 * Логика порогов:
 * - < 1 мин  → "только что"
 * - < 1 час  → "N мин назад"
 * - < 24 ч   → "N ч назад"
 * - < 48 ч   → "Вчера"
 * - иначе    → "N дн назад"
 */
internal fun formatRelativeTime(timestamp: Long): String {
    val nowMs = System.currentTimeMillis()
    val diffMs = nowMs - timestamp

    // ПОЧЕМУ: используем Long-арифметику с именованными константами — читаемо и без магических чисел
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

/**
 * Возвращает цвет статусной точки по строковому значению статуса.
 */
private fun statusColor(status: String): Color = when (status) {
    RecordingStatus.PROCESSED -> StatusColorProcessed
    RecordingStatus.PENDING_UPLOAD -> StatusColorPending
    RecordingStatus.FAILED -> StatusColorFailed
    else -> StatusColorDefault // UPLOADED и любые будущие статусы
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
        verticalArrangement = Arrangement.spacedBy(8.dp)
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
    val dotColor = statusColor(recording.status)
    // ПОЧЕМУ secondary (teal) а не primary (indigo): на тёмном surfaceVariant
    // индиго (#7C6CFF) визуально сливается, а teal (#00E5CC) создаёт яркий акцент
    val accentColor = MaterialTheme.colorScheme.secondary
    val surfaceColor = MaterialTheme.colorScheme.surfaceVariant
    val cardShape = MaterialTheme.shapes.medium

    // ПОЧЕМУ Row + clip вместо Card: Card обрезает 4dp-полоску в скруглённых углах (12dp radius).
    // Row с clip(shape) даёт тот же визуальный эффект (скруглённый прямоугольник + фон),
    // но левая цветная полоса рисуется ДО обрезки — она видна от верха до низа карточки.
    //
    // ПОЧЕМУ порядок модификаторов: clip → background → clickable → height.
    // Modifier-цепочка применяется последовательно: сначала clip задаёт форму обрезки,
    // затем background заливает именно эту форму, а clickable идёт ПОСЛЕ — тогда
    // ripple-эффект тоже обрезается по той же форме и не вылезает за скруглённые углы.
    // Если поставить clickable ДО clip, рябь будет прямоугольной — баг, заметный на тёмной теме.
    Row(
        modifier = modifier
            .fillMaxWidth()
            .padding(horizontal = 16.dp)
            .clip(cardShape)
            .background(surfaceColor)
            .clickable(onClick = onClick)
            .height(IntrinsicSize.Min)
    ) {
        // Левая акцентная полоса — 4dp индиго, на всю высоту
        Box(
            modifier = Modifier
                .width(4.dp)
                .fillMaxHeight()
                .background(accentColor)
        )

        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 12.dp, vertical = 12.dp)
        ) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                // Относительное время — единственная метаинформация на карточке.
                // Длительность убрана: она показывала "0 с" и не несла ценности.
                // Вернём её в экран деталей записи, когда он появится.
                Text(
                    text = relativeTime,
                    style = MaterialTheme.typography.titleSmall,
                    color = MaterialTheme.colorScheme.onSurface,
                    modifier = Modifier.weight(1f),
                )

                // Цветная точка статуса
                Canvas(
                    modifier = Modifier
                        .padding(start = 8.dp)
                        .size(10.dp)
                ) {
                    drawCircle(color = dotColor, radius = size.minDimension / 2f)
                }
            }

            // Транскрипция: не более 2 строк
            recording.transcription?.takeIf { it.isNotBlank() }?.let { text ->
                Text(
                    text = text,
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    maxLines = 2,
                    overflow = TextOverflow.Ellipsis,
                    modifier = Modifier.padding(top = 8.dp)
                )
            }
        }
    }
}
