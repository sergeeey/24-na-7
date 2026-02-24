package com.reflexio.app.ui.screens

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.reflexio.app.data.model.Recording
import com.reflexio.app.data.model.RecordingStatus

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
    modifier: Modifier = Modifier
) {
    if (recordings.isEmpty()) {
        Text(
            text = "Записей пока нет",
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            modifier = modifier.padding(16.dp)
        )
        return
    }
    LazyColumn(
        modifier = modifier,
        verticalArrangement = Arrangement.spacedBy(8.dp)
    ) {
        items(recordings) { recording ->
            RecordingItem(recording = recording)
        }
    }
}

@Composable
private fun RecordingItem(
    recording: Recording,
    modifier: Modifier = Modifier
) {
    val relativeTime = formatRelativeTime(recording.createdAt)

    // ПОЧЕМУ: форматируем минуты/секунды вручную вместо "Xs" —
    // "1 мин 23 с" воспринимается пользователем гораздо лучше чем "83s"
    val durationStr = if (recording.durationSeconds >= 60) {
        val m = recording.durationSeconds / 60
        val s = recording.durationSeconds % 60
        "${m} мин ${s} с"
    } else {
        "${recording.durationSeconds} с"
    }

    val dotColor = statusColor(recording.status)
    val accentColor = MaterialTheme.colorScheme.primary

    Card(
        modifier = modifier
            .fillMaxWidth()
            .padding(horizontal = 16.dp),
        colors = CardDefaults.cardColors(
            containerColor = MaterialTheme.colorScheme.surfaceVariant
        ),
        // ПОЧЕМУ: elevation = 0 оставляет карточку плоской — левая полоса становится
        // единственным визуальным акцентом, не конкурируя с тенью
        elevation = CardDefaults.cardElevation(defaultElevation = 0.dp)
    ) {
        Row(modifier = Modifier.fillMaxWidth()) {

            // ПОЧЕМУ: левая полоса реализована через Box фиксированной ширины внутри Row —
            // это надёжнее чем drawBehind (не нужно считать координаты вручную) и
            // проще чем clip + border (который рисует рамку по всему периметру)
            Box(
                modifier = Modifier
                    .width(4.dp)
                    .fillMaxHeight()
                    // ПОЧЕМУ: matchParentSize() нельзя использовать здесь (Box не в Box),
                    // поэтому используем fillMaxHeight — он растянется по содержимому Row
                    // благодаря тому, что Column рядом задаёт высоту через padding+контент
                    .padding(vertical = 0.dp)
            ) {
                // Рисуем цветную полосу через Canvas на всю высоту родительского Box
                Canvas(modifier = Modifier.matchParentSize()) {
                    drawRect(color = accentColor)
                }
            }

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
                    // Левая часть: время и длительность
                    Column(modifier = Modifier.weight(1f)) {
                        Text(
                            text = relativeTime,
                            style = MaterialTheme.typography.titleSmall,
                            color = MaterialTheme.colorScheme.onSurface
                        )
                        Text(
                            text = durationStr,
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                    }

                    // Правая часть: цветная точка статуса
                    // ПОЧЕМУ: Canvas + drawCircle вместо Box с background(CircleShape) —
                    // Canvas не создаёт лишний Composable-узел в дереве и не требует clip.
                    // padding идёт ПЕРЕД size — иначе padding уменьшает область рисования Canvas
                    Canvas(
                        modifier = Modifier
                            .padding(start = 8.dp)
                            .size(10.dp)
                    ) {
                        drawCircle(color = dotColor, radius = size.minDimension / 2f)
                    }
                }

                // Транскрипция: показываем только если есть текст, не более 2 строк
                recording.transcription?.takeIf { it.isNotBlank() }?.let { text ->
                    Text(
                        text = text,
                        style = MaterialTheme.typography.bodyMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        maxLines = 2,
                        // ПОЧЕМУ: Ellipsis обрезает длинный текст с "..." — пользователь видит
                        // что текст есть, но карточка остаётся компактной
                        overflow = TextOverflow.Ellipsis,
                        modifier = Modifier.padding(top = 8.dp)
                    )
                }
            }
        }
    }
}
