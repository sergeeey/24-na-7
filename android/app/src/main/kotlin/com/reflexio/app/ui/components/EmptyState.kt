package com.reflexio.app.ui.components

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.size
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Mic
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp

/**
 * Заглушка для пустого списка записей.
 *
 * Отображается когда у пользователя ещё нет ни одной записи.
 * Иконка микрофона намеренно приглушена (alpha 0.3) — она визуальная подсказка,
 * а не акцентный элемент, чтобы не отвлекать от CTA-текста.
 */
@Composable
fun EmptyState(modifier: Modifier = Modifier) {
    // ПОЧЕМУ: Column с verticalArrangement.Center + horizontalAlignment.CenterHorizontally —
    // самый простой способ центрировать содержимое по обеим осям без вложенных Box/Row.
    // Arrangement.spacedBy задаёт равные отступы между всеми дочерними элементами
    // декларативно, вместо ручных Spacer().
    Column(
        modifier = modifier.fillMaxSize(),
        verticalArrangement = Arrangement.spacedBy(12.dp, Alignment.CenterVertically),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        // ПОЧЕМУ: alpha = 0.3f через LocalContentColor (tint) — Material3-способ приглушить иконку.
        // Прямое hardcode-значение цвета сломает поддержку светлой темы,
        // а tint с alpha наследует правильный onSurface/onBackground из темы.
        Icon(
            imageVector = Icons.Filled.Mic,
            contentDescription = null, // декоративная иконка — текст рядом уже всё объясняет
            modifier = Modifier.size(56.dp),
            tint = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.3f),
        )

        Text(
            text = "Записей пока нет",
            style = MaterialTheme.typography.titleMedium,
            color = MaterialTheme.colorScheme.onSurface,
        )

        // ПОЧЕМУ: onSurfaceVariant — семантически правильный цвет Material3 для
        // вспомогательного/подсказочного текста (менее акцентный, чем onSurface).
        // Не используем alpha вручную — тема уже настроена на нужный контраст.
        Text(
            text = "Нажмите кнопку записи, чтобы начать",
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
    }
}
