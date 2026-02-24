package com.reflexio.app.ui.components

import androidx.compose.animation.animateColorAsState
import androidx.compose.animation.core.tween
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.Checkbox
import androidx.compose.material3.CheckboxDefaults
import androidx.compose.material3.ElevatedCard
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.hapticfeedback.HapticFeedbackType
import androidx.compose.ui.platform.LocalHapticFeedback
import androidx.compose.ui.text.style.TextDecoration
import androidx.compose.ui.unit.dp

// ПОЧЕМУ отдельный компонент: ActionItemCard переиспользуется в DailySummaryScreen
// и позже в RecordingDetailScreen (при клике на карточку записи).
// Аналогия: это как "виджет задачи" в Todoist — минимальный, но кликабельный.

private val ColorTeal = Color(0xFF00E5CC)

/**
 * Интерактивная карточка задачи из LLM enrichment.
 *
 * @param taskText текст задачи
 * @param urgency уровень срочности: "high", "medium", "low"
 * @param isCompleted начальное состояние выполнения
 * @param onToggle callback при изменении состояния checkbox
 */
@Composable
fun ActionItemCard(
    taskText: String,
    urgency: String = "medium",
    isCompleted: Boolean = false,
    onToggle: (Boolean) -> Unit = {},
) {
    val haptic = LocalHapticFeedback.current

    // ПОЧЕМУ animateColorAsState: плавный переход фона при отметке задачи
    // вместо мгновенного переключения — ощущение "завершённости"
    val containerColor by animateColorAsState(
        targetValue = if (isCompleted) MaterialTheme.colorScheme.surface
                      else MaterialTheme.colorScheme.surfaceVariant,
        animationSpec = tween(300),
        label = "cardColor",
    )

    ElevatedCard(
        modifier = Modifier.fillMaxWidth().padding(vertical = 4.dp),
        colors = CardDefaults.elevatedCardColors(containerColor = containerColor),
    ) {
        Row(
            modifier = Modifier.padding(12.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Checkbox(
                checked = isCompleted,
                onCheckedChange = { checked ->
                    onToggle(checked)
                    // ПОЧЕМУ haptic именно при check: тактильный отклик на
                    // "завершение задачи" создаёт ощущение достижения (микро-награда).
                    // При uncheck не вибрируем — снятие галочки не должно "награждать".
                    if (checked) {
                        haptic.performHapticFeedback(HapticFeedbackType.LongPress)
                    }
                },
                colors = CheckboxDefaults.colors(
                    checkedColor = ColorTeal,
                    uncheckedColor = MaterialTheme.colorScheme.outline,
                ),
            )
            Spacer(modifier = Modifier.width(8.dp))
            Column(modifier = Modifier.weight(1f)) {
                Text(
                    text = taskText,
                    style = MaterialTheme.typography.bodyLarge,
                    color = if (isCompleted) MaterialTheme.colorScheme.outline
                            else MaterialTheme.colorScheme.onSurface,
                    textDecoration = if (isCompleted) TextDecoration.LineThrough else TextDecoration.None,
                )
                if (urgency == "high" && !isCompleted) {
                    // ПОЧЕМУ Surface вместо Badge: Badge в Compose BOM 2023.10 требует
                    // @OptIn(ExperimentalMaterial3Api::class) и нестабилен. Surface надёжнее.
                    androidx.compose.material3.Surface(
                        color = MaterialTheme.colorScheme.error,
                        shape = androidx.compose.foundation.shape.RoundedCornerShape(4.dp),
                        modifier = Modifier.padding(top = 4.dp),
                    ) {
                        Text(
                            "Важно",
                            modifier = Modifier.padding(horizontal = 6.dp, vertical = 2.dp),
                            style = MaterialTheme.typography.labelSmall,
                            color = MaterialTheme.colorScheme.onError,
                        )
                    }
                }
            }
        }
    }
}
