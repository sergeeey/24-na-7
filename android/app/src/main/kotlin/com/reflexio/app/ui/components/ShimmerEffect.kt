package com.reflexio.app.ui.components

import androidx.compose.animation.core.LinearEasing
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp

// ПОЧЕМУ shimmer а не CircularProgressIndicator:
// Скелетная загрузка показывает ФОРМУ будущего контента (как рентген),
// а спиннер говорит только "жди". Shimmer снижает perceived wait time на ~35%
// (исследование Facebook 2014, подтверждено Google Material Design guidelines).

/**
 * Shimmer placeholder для загружающегося контента.
 * Имитирует форму строки текста или блока.
 */
@Composable
fun ShimmerLine(
    modifier: Modifier = Modifier,
    height: Dp = 16.dp,
) {
    val transition = rememberInfiniteTransition(label = "shimmer")
    val translateX by transition.animateFloat(
        initialValue = -300f,
        targetValue = 600f,
        animationSpec = infiniteRepeatable(
            animation = tween(durationMillis = 1200, easing = LinearEasing),
            repeatMode = RepeatMode.Restart,
        ),
        label = "shimmerTranslate",
    )

    val shimmerColors = listOf(
        Color(0xFF1C2333),  // surfaceVariant (совпадает с темой)
        Color(0xFF2A3040),  // lighter
        Color(0xFF1C2333),  // back to surfaceVariant
    )

    Box(
        modifier = modifier
            .fillMaxWidth()
            .height(height)
            .clip(RoundedCornerShape(4.dp))
            .background(
                Brush.linearGradient(
                    colors = shimmerColors,
                    start = Offset(translateX, 0f),
                    end = Offset(translateX + 300f, 0f),
                )
            ),
    )
}

/**
 * Скелет-загрузка экрана дайджеста: имитирует заголовок + текст + чипсы + задачи.
 */
@Composable
fun DigestShimmerSkeleton(modifier: Modifier = Modifier) {
    Column(modifier = modifier.padding(top = 8.dp)) {
        // "Итог" заголовок
        ShimmerLine(modifier = Modifier.fillMaxWidth(0.3f), height = 20.dp)
        Spacer(modifier = Modifier.height(8.dp))
        // Summary block
        ShimmerLine(height = 14.dp)
        Spacer(modifier = Modifier.height(6.dp))
        ShimmerLine(height = 14.dp)
        Spacer(modifier = Modifier.height(6.dp))
        ShimmerLine(modifier = Modifier.fillMaxWidth(0.7f), height = 14.dp)

        Spacer(modifier = Modifier.height(24.dp))

        // "Темы" заголовок
        ShimmerLine(modifier = Modifier.fillMaxWidth(0.4f), height = 20.dp)
        Spacer(modifier = Modifier.height(8.dp))
        // Chips row
        ShimmerLine(modifier = Modifier.fillMaxWidth(0.8f), height = 32.dp)

        Spacer(modifier = Modifier.height(24.dp))

        // "Действия" заголовок
        ShimmerLine(modifier = Modifier.fillMaxWidth(0.35f), height = 20.dp)
        Spacer(modifier = Modifier.height(8.dp))
        // Task cards
        repeat(3) {
            ShimmerLine(height = 48.dp)
            Spacer(modifier = Modifier.height(8.dp))
        }
    }
}
