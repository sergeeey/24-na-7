package com.reflexio.app.ui.components

import androidx.compose.animation.core.LinearEasing
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.size
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Mic
import androidx.compose.material.icons.rounded.Stop
import androidx.compose.material3.Icon
import androidx.compose.material3.LargeFloatingActionButton
import androidx.compose.material3.FloatingActionButtonDefaults
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.hapticfeedback.HapticFeedbackType
import androidx.compose.ui.platform.LocalHapticFeedback
import androidx.compose.ui.unit.dp

// Цвета FAB вынесены как константы, а не в theme —
// это UI-специфичные значения компонента, не часть дизайн-системы.
private val ColorTeal = Color(0xFF00E5CC)
private val ColorRed = Color(0xFFFF6B6B)

// ПОЧЕМУ 96.dp: LargeFloatingActionButton имеет размер 96dp по Material3 спеке,
// Canvas должен совпадать с этим размером чтобы кольцо рисовалось вокруг FAB,
// а не обрезалось по границам Box.
private val FabContainerSize = 96.dp

// ПОЧЕМУ 2x: кольцо пульса должно расширяться до ~2x радиуса FAB (48dp → 96dp),
// это визуально "естественный" диапазон расширения — не слишком резкий и не вялый.
private const val PulseMaxRadiusMultiplier = 2.0f

// ПОЧЕМУ 1.5f секунды: ощущение дыхания/пульса. Меньше — тревожно, больше — вяло.
private const val PulseDurationMs = 1500

/**
 * FloatingActionButton для управления записью голоса.
 *
 * В состоянии покоя — teal кнопка с иконкой микрофона.
 * В состоянии записи — красная кнопка со стоп-иконкой и пульсирующим кольцом.
 *
 * @param isRecording текущее состояние: идёт ли запись
 * @param onClick колбэк нажатия (toggle записи на стороне ViewModel)
 * @param modifier стандартный Compose modifier для позиционирования снаружи
 */
@Composable
fun RecordingFab(
    isRecording: Boolean,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
) {
    // ПОЧЕМУ haptic: тактильный отклик при старте/стопе записи — пользователь
    // чувствует что нажатие "принято" физически, даже не глядя на экран.
    val haptic = LocalHapticFeedback.current

    // ПОЧЕМУ Box а не просто FAB: нам нужно нарисовать кольцо ПОЗАДИ кнопки.
    // В Compose слои в Box рисуются в порядке объявления — первый снизу, последний сверху.
    // Если поставить Canvas после FAB — кольцо будет поверх кнопки и перекроет иконку.
    Box(
        modifier = modifier.size(FabContainerSize),
        contentAlignment = Alignment.Center,
    ) {
        // --- Слой 1: пульсирующее кольцо (только когда идёт запись) ---
        if (isRecording) {
            PulseRing(ringColor = ColorRed)
        }

        // --- Слой 2: сама кнопка ---
        LargeFloatingActionButton(
            onClick = {
                haptic.performHapticFeedback(HapticFeedbackType.LongPress)
                onClick()
            },
            // ПОЧЕМУ containerColor вместо тему: нам нужен точный hex-цвет из брендинга,
            // а не тот что Material3 подберёт автоматически по colorScheme.
            containerColor = if (isRecording) ColorRed else ColorTeal,
            contentColor = Color.White,
            elevation = FloatingActionButtonDefaults.elevation(
                defaultElevation = 6.dp,
                pressedElevation = 12.dp,
            ),
        ) {
            Icon(
                imageVector = if (isRecording) Icons.Rounded.Stop else Icons.Default.Mic,
                contentDescription = if (isRecording) "Остановить запись" else "Начать запись",
                // ПОЧЕМУ 32.dp: LargeFloatingActionButton = 96dp контейнер,
                // иконка 32dp — стандартное соотношение 1:3 по Material3 гайдлайнам.
            )
        }
    }
}

/**
 * Анимированное пульсирующее кольцо вокруг FAB.
 *
 * Рисуется через Canvas позади кнопки.
 * Кольцо растёт от размера FAB наружу и одновременно становится прозрачным —
 * создаёт эффект "звуковой волны" расходящейся от микрофона.
 *
 * @param ringColor цвет кольца (обычно совпадает с цветом FAB)
 */
@Composable
private fun PulseRing(ringColor: Color) {
    // ПОЧЕМУ rememberInfiniteTransition: это Compose-способ создать бесконечную анимацию.
    // Аналогия из security: это как watchdog-таймер — сам перезапускается, не нужно следить.
    val infiniteTransition = rememberInfiniteTransition(label = "pulse")

    // progress: 0.0 → 1.0 → 0.0 → ... каждые PulseDurationMs миллисекунд
    // ПОЧЕМУ LinearEasing: для пульса нужно равномерное расширение.
    // EaseInOut выглядит "резинистым" — не то ощущение для звуковой волны.
    val progress by infiniteTransition.animateFloat(
        initialValue = 0f,
        targetValue = 1f,
        animationSpec = infiniteRepeatable(
            animation = tween(durationMillis = PulseDurationMs, easing = LinearEasing),
            // ПОЧЕМУ Restart а не Reverse: волна всегда идёт ОТ центра НАРУЖУ.
            // Reverse заставил бы её возвращаться обратно — визуально неправильно.
            repeatMode = RepeatMode.Restart,
        ),
        label = "pulseProgress",
    )

    Canvas(modifier = Modifier.size(FabContainerSize)) {
        // Радиус FAB в пикселях (половина контейнера)
        val fabRadiusPx = size.minDimension / 2f

        // Текущий радиус кольца: от fabRadiusPx до fabRadiusPx * PulseMaxRadiusMultiplier
        val currentRadius = fabRadiusPx + (fabRadiusPx * (PulseMaxRadiusMultiplier - 1f) * progress)

        // ПОЧЕМУ альфа инвертирована к progress: кольцо должно быть ярким у FAB
        // и исчезать по мере расширения — как реальная звуковая волна затухает с расстоянием.
        val alpha = (1f - progress) * 0.6f

        drawCircle(
            color = ringColor.copy(alpha = alpha),
            radius = currentRadius,
            center = Offset(size.width / 2f, size.height / 2f),
            // ПОЧЕМУ Stroke а не filled circle: нам нужно именно кольцо (контур),
            // а не закрашенный круг который перекроет содержимое.
            style = Stroke(width = 4.dp.toPx()),
        )
    }
}
