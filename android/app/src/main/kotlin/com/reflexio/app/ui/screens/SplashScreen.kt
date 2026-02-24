package com.reflexio.app.ui.screens

import androidx.compose.animation.core.Animatable
import androidx.compose.animation.core.Easing
import androidx.compose.animation.core.tween
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.draw.scale
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Rect
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.StrokeJoin
import androidx.compose.ui.graphics.drawscope.DrawScope
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.launch

// Цвета вынесены как константы — не нужен Compose-контекст, используются и в Canvas и в тексте
private val ColorIndigoPrimary = Color(0xFF7C6CFF)
private val ColorTealSecondary = Color(0xFF00E5CC)
private val ColorBackground = Color(0xFF0D1117)

// ПОЧЕМУ EaseOutBack через кастомный Easing:
// Стандартный `EaseOutBack` доступен только в Compose 1.5+.
// Чтобы не зависеть от версии, реализуем формулу вручную.
// EaseOutBack даёт "overshoot" эффект — логотип немного перелетает целевой размер и
// возвращается. Это создаёт ощущение "живости" и фирменный feel для splash-экрана.
private val EaseOutBackEasing: Easing = Easing { fraction ->
    val c1 = 1.70158f
    val c3 = c1 + 1f
    // Формула cubic overshoot из спецификации CSS easing functions
    val t = fraction - 1f
    c3 * t * t * t + c1 * t * t + 1f
}

/**
 * Сплэш-экран приложения Reflexio.
 *
 * Показывает анимированный логотип и брендинг при старте приложения.
 * Последовательность анимации (~1.8 сек):
 * 1. Масштаб 0.8 → 1.0 с EaseOutBack (overshoot) за 800ms
 * 2. Fade in 0 → 1 за 600ms (параллельно со scale)
 * 3. Пауза 400ms
 * 4. Fade out 1 → 0 за 400ms
 * 5. Вызов [onSplashFinished]
 *
 * @param onSplashFinished Callback, вызывается после завершения анимации.
 *        Навигация на следующий экран — ответственность вызывающего кода.
 * @param modifier Стандартный Compose modifier.
 */
@Composable
fun SplashScreen(
    onSplashFinished: () -> Unit,
    modifier: Modifier = Modifier,
) {
    // ПОЧЕМУ два отдельных Animatable, а не один AnimatedVisibility:
    // AnimatedVisibility управляет alpha и scale совместно, что не позволяет задать
    // разные easing/duration для каждого. Здесь scale нужен EaseOutBack (overshoot),
    // а alpha — линейный. Два Animatable дают полный контроль над каждой анимацией.
    val alpha = remember { Animatable(0f) }
    val scale = remember { Animatable(0.8f) }

    // ПОЧЕМУ LaunchedEffect(Unit):
    // Unit как ключ — эффект запускается ровно один раз при появлении composable в
    // composition и не перезапускается при рекомпозиции. Это стандартный паттерн для
    // "fire-once" анимаций на старте экрана.
    LaunchedEffect(Unit) {
        // Запускаем scale и alpha параллельно через launch — они независимы,
        // но имеют разную длительность. После обоих ждём паузу и делаем fade out.
        launch {
            scale.animateTo(
                targetValue = 1f,
                animationSpec = tween(
                    durationMillis = 800,
                    easing = EaseOutBackEasing,
                ),
            )
        }
        // ПОЧЕМУ alpha запускается без launch (в основной корутине):
        // Fade in (600ms) короче scale (800ms). Запускаем alpha в основной корутине —
        // она завершится первой, и мы продолжим к следующим шагам.
        // scale при этом продолжает работать параллельно благодаря launch выше.
        alpha.animateTo(
            targetValue = 1f,
            animationSpec = tween(
                durationMillis = 600,
                easing = EaseOutBackEasing,
            ),
        )

        // Пауза — пользователь видит готовый логотип
        kotlinx.coroutines.delay(400L)

        // Fade out — всё исчезает плавно
        alpha.animateTo(
            targetValue = 0f,
            animationSpec = tween(durationMillis = 400),
        )

        onSplashFinished()
    }

    Box(
        modifier = modifier
            .fillMaxSize()
            .background(ColorBackground),
        contentAlignment = Alignment.Center,
    ) {
        Column(
            modifier = Modifier
                .alpha(alpha.value)
                .scale(scale.value),
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            // Логотип R-монограмма на Canvas
            Canvas(modifier = Modifier.size(96.dp)) {
                drawReflexioLogo(this)
            }

            Spacer(modifier = Modifier.height(20.dp))

            Text(
                text = "Reflexio",
                style = MaterialTheme.typography.titleLarge,
                color = ColorIndigoPrimary,
            )

            Spacer(modifier = Modifier.height(6.dp))

            Text(
                text = "24/7",
                style = MaterialTheme.typography.bodyMedium,
                color = ColorTealSecondary,
            )
        }

        // ПОЧЕМУ Text "Голосовой дневник" вынесен за Column и прижат к низу:
        // Он семантически отделён от логотипной группы — это подзаголовок приложения,
        // а не часть бренда. Используем Box + padding вместо Column spacer,
        // чтобы прижать к нижнему краю независимо от высоты центральной группы.
        Text(
            text = "Голосовой дневник",
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            modifier = Modifier
                .align(Alignment.BottomCenter)
                .padding(bottom = 40.dp)
                .alpha(alpha.value),
        )
    }
}

/**
 * Рисует R-монограмму логотипа Reflexio внутри переданного DrawScope.
 *
 * Состав логотипа:
 * - Два концентрических кольца (orbital rings) в индиго
 * - Внутренний круг с заливкой (очень прозрачный)
 * - Буква "R": вертикальный штрих + верхняя арка + диагональная нога в teal
 * - Три декоративных точки ниже буквы в teal
 *
 * Вынесено в отдельную функцию (не лямбду Canvas) для читаемости и тестируемости.
 */
private fun drawReflexioLogo(scope: DrawScope) {
    with(scope) {
        val cx = size.width / 2f
        val cy = size.height / 2f

        // === КОНЦЕНТРИЧЕСКИЕ КОЛЬЦА ===

        // ПОЧЕМУ strokeWidth в пикселях через .toPx():
        // Canvas DrawScope работает в пикселях, а dp — логические единицы.
        // Конвертация через density гарантирует правильный размер на любом экране.

        // Внешнее кольцо — тонкое, почти прозрачное
        drawCircle(
            color = ColorIndigoPrimary.copy(alpha = 0.40f),
            radius = cx * 0.92f,
            center = Offset(cx, cy),
            style = Stroke(width = 1.5.dp.toPx()),
        )

        // Внутреннее кольцо — чуть ярче, ближе к центру
        drawCircle(
            color = ColorIndigoPrimary.copy(alpha = 0.65f),
            radius = cx * 0.72f,
            center = Offset(cx, cy),
            style = Stroke(width = 2.0.dp.toPx()),
        )

        // Заполненный внутренний круг — очень прозрачный, создаёт "объём"
        drawCircle(
            color = ColorIndigoPrimary.copy(alpha = 0.15f),
            radius = cx * 0.52f,
            center = Offset(cx, cy),
            style = Stroke(width = 2.5.dp.toPx()),
        )

        // === БУКВА "R" ===

        // ПОЧЕМУ Path вместо отдельных drawLine вызовов:
        // Path позволяет задать StrokeCap и StrokeJoin единожды для всей фигуры,
        // что даёт единый стиль скруглений на всех углах буквы.
        // С drawLine пришлось бы дублировать параметры для каждого сегмента.

        val strokeWidth = 3.5.dp.toPx()
        val letterPaint = Stroke(
            width = strokeWidth,
            cap = StrokeCap.Round,
            join = StrokeJoin.Round,
        )

        // Основная часть буквы R: вертикальный штрих + арка (индиго)
        val rMainPath = Path().apply {
            // Вертикальный штрих: сверху вниз
            moveTo(cx - 8.dp.toPx(), cy - 10.dp.toPx())
            lineTo(cx - 8.dp.toPx(), cy + 10.dp.toPx())

            // Арка (P-образный выступ):
            // Начало — верх вертикального штриха
            moveTo(cx - 8.dp.toPx(), cy - 10.dp.toPx())
            // Горизонталь вправо
            lineTo(cx + 1.dp.toPx(), cy - 10.dp.toPx())
            // ПОЧЕМУ arcTo через Rect:
            // arcTo требует bounding box эллипса. Наша арка — полуокружность радиусом ~8dp.
            // sweepAngle = 180 рисует правую половину окружности сверху вниз.
            arcTo(
                rect = Rect(
                    left = cx - 7.dp.toPx(),
                    top = cy - 10.dp.toPx(),
                    right = cx + 9.dp.toPx(),
                    bottom = cy + 6.dp.toPx(),
                ),
                startAngleDegrees = -90f,  // начало сверху
                sweepAngleDegrees = 180f,  // по часовой — вниз и влево
                forceMoveTo = false,
            )
            // Замыкаем арку обратно к вертикальному штриху
            lineTo(cx - 8.dp.toPx(), cy + 6.dp.toPx())
        }

        drawPath(
            path = rMainPath,
            color = ColorIndigoPrimary,
            style = letterPaint,
        )

        // Диагональная нога буквы R — в teal, создаёт фирменный акцент
        val rLegPath = Path().apply {
            moveTo(cx - 3.dp.toPx(), cy + 6.dp.toPx())
            lineTo(cx + 8.dp.toPx(), cy + 16.dp.toPx())
        }

        drawPath(
            path = rLegPath,
            color = ColorTealSecondary,
            style = letterPaint,
        )

        // === ТРИ ДЕКОРАТИВНЫЕ ТОЧКИ ===

        // ПОЧЕМУ точки именно ниже центра на 20dp:
        // Нога буквы R доходит до cy+16dp. Точки на cy+20dp образуют
        // визуальный "footer" логотипа — небольшой отступ от ноги.
        val dotRadius = 1.8.dp.toPx()
        val dotY = cy + 20.dp.toPx()
        val dotSpacing = 6.dp.toPx()

        listOf(cx - dotSpacing, cx, cx + dotSpacing).forEach { dotX ->
            drawCircle(
                color = ColorTealSecondary,
                radius = dotRadius,
                center = Offset(dotX, dotY),
            )
        }
    }
}

// ПОЧЕМУ Preview без onSplashFinished:
// Preview не может вызывать callback — Compose Preview не выполняет LaunchedEffect.
// Передаём пустую лямбду, чтобы увидеть финальный вид экрана (alpha=0 в начале —
// поэтому preview может выглядеть пустым; это нормально, анимация работает только на устройстве).
@Preview(showBackground = true, backgroundColor = 0xFF0D1117)
@Composable
private fun SplashScreenPreview() {
    SplashScreen(onSplashFinished = {})
}
