package com.reflexio.app.ui.components

import androidx.compose.animation.core.FastOutSlowInEasing
import androidx.compose.animation.core.LinearEasing
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Mic
import androidx.compose.material.icons.filled.MicOff
import androidx.compose.material.icons.rounded.Stop
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.BlendMode
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.drawscope.DrawScope
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.drawscope.drawIntoCanvas
import androidx.compose.ui.graphics.nativeCanvas
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.hapticfeedback.HapticFeedbackType
import androidx.compose.ui.platform.LocalHapticFeedback
import androidx.compose.ui.unit.dp
import com.reflexio.app.BuildConfig
import com.reflexio.app.domain.network.ServerEndpointResolver
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import okhttp3.OkHttpClient
import okhttp3.Request
import org.json.JSONObject
import java.time.LocalDate
import java.util.concurrent.TimeUnit
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlin.math.PI
import kotlin.math.cos
import kotlin.math.min
import kotlin.math.sin

private data class WheelDomain(
    val key: String,
    val label: String,
    val color: Color,
)

private val WHEEL_DOMAINS = listOf(
    WheelDomain("work", "Работа", Color(0xFF7C6CFF)),
    WheelDomain("health", "Здоровье", Color(0xFF00E5CC)),
    WheelDomain("family", "Семья", Color(0xFFFFB74D)),
    WheelDomain("finance", "Финансы", Color(0xFF4CAF50)),
    WheelDomain("psychology", "Психология", Color(0xFFE040FB)),
    WheelDomain("relations", "Отношения", Color(0xFFFF6B6B)),
    WheelDomain("growth", "Рост", Color(0xFF29B6F6)),
    WheelDomain("leisure", "Отдых", Color(0xFFFFF176)),
)

private enum class WheelLoadState {
    LOADING,
    READY,
    EMPTY,
    ERROR,
}

private data class WheelUiModel(
    val state: WheelLoadState,
    val scores: FloatArray,
    val helperText: String? = null,
)

@Composable
fun BalanceWheelVisualizer(
    baseHttpUrl: String,
    isRecording: Boolean = false,
    hasPermission: Boolean = true,
    onToggleRecording: () -> Unit = {},
    onRequestPermission: () -> Unit = {},
    showCenterControl: Boolean = true,
    modifier: Modifier = Modifier,
) {
    var wheelModel by remember {
        mutableStateOf(
            WheelUiModel(
                state = WheelLoadState.LOADING,
                scores = FloatArray(WHEEL_DOMAINS.size) { 0f },
            )
        )
    }

    val infiniteTransition = rememberInfiniteTransition(label = "wheelPulse")
    val pulseProgress by infiniteTransition.animateFloat(
        initialValue = 0f,
        targetValue = 1f,
        animationSpec = infiniteRepeatable(
            animation = tween(
                durationMillis = if (isRecording) 2600 else 4200,
                easing = LinearEasing,
            ),
            repeatMode = RepeatMode.Restart,
        ),
        label = "pulseProgress",
    )
    val secondaryPulseProgress by infiniteTransition.animateFloat(
        initialValue = 0.35f,
        targetValue = 1.35f,
        animationSpec = infiniteRepeatable(
            animation = tween(
                durationMillis = if (isRecording) 3400 else 5200,
                easing = LinearEasing,
            ),
            repeatMode = RepeatMode.Restart,
        ),
        label = "secondaryPulseProgress",
    )
    val breathingScale by animateFloatAsState(
        targetValue = if (isRecording) 1.025f else 1f,
        animationSpec = tween(durationMillis = 1400, easing = FastOutSlowInEasing),
        label = "breathingScale",
    )
    val wheelAlpha by animateFloatAsState(
        targetValue = when (wheelModel.state) {
            WheelLoadState.READY -> if (isRecording) 1f else 0.94f
            WheelLoadState.LOADING -> 0.78f
            WheelLoadState.EMPTY -> 0.62f
            WheelLoadState.ERROR -> 0.48f
        },
        animationSpec = tween(durationMillis = 700),
        label = "wheelAlpha",
    )

    LaunchedEffect(baseHttpUrl, isRecording) {
        wheelModel = wheelModel.copy(state = WheelLoadState.LOADING, helperText = null)
        do {
            val fetched = withContext(Dispatchers.IO) { fetchWheelScores(baseHttpUrl) }
            wheelModel = fetched
            if (
                fetched.state != WheelLoadState.ERROR ||
                !ServerEndpointResolver.isLocalUrl(baseHttpUrl) ||
                !isActive
            ) {
                break
            }
            delay(5_000)
        } while (true)
    }

    Box(
        modifier = modifier
            .fillMaxSize()
            .clip(RoundedCornerShape(36.dp))
            .background(
                Brush.radialGradient(
                    colors = listOf(
                        Color(0x66234A66),
                        Color(0x33142436),
                        Color(0x00071018),
                    ),
                    radius = 1600f,
                ),
            )
            .drawBehind {
                drawRect(
                    brush = Brush.verticalGradient(
                        colors = listOf(
                            Color.White.copy(alpha = 0.05f),
                            Color.Transparent,
                            Color.Black.copy(alpha = 0.16f),
                        ),
                    ),
                )
            },
        contentAlignment = Alignment.Center,
    ) {
        Canvas(
            modifier = Modifier
                .fillMaxSize()
                .graphicsLayer {
                    scaleX = breathingScale
                    scaleY = breathingScale
                    alpha = wheelAlpha
                },
        ) {
            val cx = size.width / 2f
            val cy = size.height / 2f
            val maxR = min(size.width, size.height) * 0.462f
            val n = WHEEL_DOMAINS.size
            val readyState = wheelModel.state == WheelLoadState.READY
            val waveStartRadius = maxR * 0.17f

            drawWheelAtmosphere(cx, cy, maxR, isRecording, pulseProgress, secondaryPulseProgress)
            if (isRecording) {
                drawRecordingWaves(
                    cx = cx,
                    cy = cy,
                    startRadius = waveStartRadius,
                    maxRadius = maxR * 0.90f,
                    primaryProgress = pulseProgress,
                    secondaryProgress = secondaryPulseProgress,
                )
            }
            drawGrid(cx, cy, maxR, n)
            drawFilledPolygon(cx, cy, maxR, n, wheelModel.scores, readyState)
            drawNodes(cx, cy, maxR, n, wheelModel.scores, readyState)
            drawLabels(cx, cy, maxR, n, wheelModel.scores, readyState)
            drawInnerVignette(cx, cy, maxR)
        }

        if (showCenterControl) {
            WheelCenterControl(
                isRecording = isRecording,
                hasPermission = hasPermission,
                onToggleRecording = onToggleRecording,
                onRequestPermission = onRequestPermission,
            )
        }
    }
}

@Composable
private fun WheelCenterControl(
    isRecording: Boolean,
    hasPermission: Boolean,
    onToggleRecording: () -> Unit,
    onRequestPermission: () -> Unit,
) {
    val haptic = LocalHapticFeedback.current
    val interactionSource = remember { MutableInteractionSource() }
    val infiniteTransition = rememberInfiniteTransition(label = "centerButtonPulse")
    val haloPulse by infiniteTransition.animateFloat(
        initialValue = 0.92f,
        targetValue = 1.08f,
        animationSpec = infiniteRepeatable(
            animation = tween(
                durationMillis = if (isRecording) 1200 else 2200,
                easing = FastOutSlowInEasing,
            ),
            repeatMode = RepeatMode.Reverse,
        ),
        label = "haloPulse",
    )

    val accentColor = when {
        !hasPermission -> MaterialTheme.colorScheme.outline
        isRecording -> Color(0xFFFF6B6B)
        else -> Color(0xFF42E5C2)
    }
    val coreScale by animateFloatAsState(
        targetValue = if (isRecording) 1.06f else 1f,
        animationSpec = tween(durationMillis = 900, easing = FastOutSlowInEasing),
        label = "coreScale",
    )

    Box(
        modifier = Modifier.size(112.dp),
        contentAlignment = Alignment.Center,
    ) {
        Surface(
            modifier = Modifier
                .size(76.dp)
                .graphicsLayer {
                    scaleX = coreScale * haloPulse
                    scaleY = coreScale * haloPulse
                }
                .clip(CircleShape)
                .drawBehind {
                    drawCircle(
                        brush = Brush.radialGradient(
                            colors = listOf(
                                accentColor.copy(alpha = if (isRecording) 0.20f else 0.08f),
                                Color.Transparent,
                            ),
                            radius = size.minDimension * 1.45f,
                            center = Offset(size.width * 0.5f, size.height * 0.5f),
                        ),
                    )
                    drawCircle(
                        brush = Brush.radialGradient(
                            colors = listOf(
                                Color.White.copy(alpha = 0.22f),
                                Color.Transparent,
                            ),
                            radius = size.minDimension * 0.68f,
                            center = Offset(size.width * 0.36f, size.height * 0.28f),
                        ),
                    )
                    drawCircle(
                        brush = metallicRimBrush(this.size.minDimension, accentColor, isRecording),
                        style = Stroke(width = 3.dp.toPx()),
                    )
                    drawCircle(
                        color = Color.Black.copy(alpha = 0.24f),
                        radius = size.minDimension * 0.36f,
                        center = Offset(size.width * 0.5f, size.height * 0.60f),
                    )
                }
                .clickable(
                    enabled = true,
                    interactionSource = interactionSource,
                    indication = null,
                ) {
                    haptic.performHapticFeedback(HapticFeedbackType.LongPress)
                    if (hasPermission) onToggleRecording() else onRequestPermission()
                },
            shape = CircleShape,
            color = Color(0xCC101B24),
            tonalElevation = 0.dp,
            shadowElevation = 12.dp,
        ) {
            Box(
                modifier = Modifier
                    .fillMaxSize()
                    .background(
                        Brush.radialGradient(
                            colors = listOf(
                                accentColor.copy(alpha = if (hasPermission) 0.94f else 0.28f),
                                accentColor.copy(alpha = if (hasPermission) 0.42f else 0.14f),
                                Color.Transparent,
                            ),
                        ),
                    ),
                contentAlignment = Alignment.Center,
            ) {
                Icon(
                    imageVector = when {
                        !hasPermission -> Icons.Default.MicOff
                        isRecording -> Icons.Rounded.Stop
                        else -> Icons.Default.Mic
                    },
                    contentDescription = when {
                        !hasPermission -> "Запросить доступ к микрофону"
                        isRecording -> "Остановить запись"
                        else -> "Начать запись"
                    },
                    tint = Color.White.copy(alpha = if (hasPermission) 1f else 0.74f),
                    modifier = Modifier.size(24.dp),
                )
            }
        }
    }
}

private fun metallicRimBrush(size: Float, accentColor: Color, isRecording: Boolean): Brush {
    return Brush.sweepGradient(
        colors = listOf(
            Color.White.copy(alpha = 0.86f),
            accentColor.copy(alpha = if (isRecording) 0.92f else 0.56f),
            Color(0xFF18242E),
            accentColor.copy(alpha = if (isRecording) 0.54f else 0.28f),
            Color.White.copy(alpha = 0.66f),
        ),
        center = Offset(size / 2f, size / 2f),
    )
}

private fun DrawScope.drawWheelAtmosphere(
    cx: Float,
    cy: Float,
    maxR: Float,
    isRecording: Boolean,
    pulseProgress: Float,
    secondaryPulseProgress: Float,
) {
    drawCircle(
        brush = Brush.radialGradient(
            colors = listOf(
                Color(0x5442E5C2),
                Color(0x1E47B8FF),
                Color.Transparent,
            ),
            center = Offset(cx, cy),
            radius = maxR * 1.42f,
        ),
        radius = maxR * 1.42f,
        center = Offset(cx, cy),
        blendMode = BlendMode.Screen,
    )

    val ringAlpha = if (isRecording) 0.16f else 0.05f
    drawCircle(
        color = Color(0xFF42E5C2).copy(alpha = ringAlpha * (1f - pulseProgress)),
        radius = maxR * (0.96f + pulseProgress * 0.20f),
        center = Offset(cx, cy),
        style = Stroke(width = 1.5f),
    )
    drawCircle(
        color = Color(0xFF8ED8F8).copy(alpha = ringAlpha * (1.1f - secondaryPulseProgress.coerceAtMost(1f))),
        radius = maxR * secondaryPulseProgress.coerceAtLeast(0.86f),
        center = Offset(cx, cy),
        style = Stroke(width = 1.0f),
    )
}

private fun DrawScope.drawRecordingWaves(
    cx: Float,
    cy: Float,
    startRadius: Float,
    maxRadius: Float,
    primaryProgress: Float,
    secondaryProgress: Float,
) {
    fun drawWave(progress: Float, color: Color, widthPx: Float) {
        val clamped = progress.coerceIn(0f, 1f)
        val radius = startRadius + (maxRadius - startRadius) * clamped
        val alpha = (1f - clamped) * 0.34f
        drawCircle(
            color = color.copy(alpha = alpha),
            radius = radius,
            center = Offset(cx, cy),
            style = Stroke(width = widthPx),
        )
    }

    drawWave(primaryProgress, Color(0xFF42E5C2), 3.0f)
    drawWave((primaryProgress + 0.33f) % 1f, Color(0xFF8ED8F8), 2.2f)
    drawWave((secondaryProgress % 1f), Color(0xFFFF6B6B), 1.6f)
}

private fun DrawScope.drawInnerVignette(cx: Float, cy: Float, maxR: Float) {
    drawCircle(
        brush = Brush.radialGradient(
            colors = listOf(
                Color.Transparent,
                Color.Black.copy(alpha = 0.10f),
                Color.Black.copy(alpha = 0.22f),
            ),
            center = Offset(cx, cy),
            radius = maxR * 1.42f,
        ),
        radius = maxR * 1.42f,
        center = Offset(cx, cy),
    )
}

private fun DrawScope.drawGrid(cx: Float, cy: Float, maxR: Float, n: Int) {
    val gridColor = Color.White.copy(alpha = 0.12f)
    repeat(4) { ring ->
        val r = maxR * (ring + 1).toFloat() / 4f
        drawCircle(
            color = gridColor,
            radius = r,
            center = Offset(cx, cy),
            style = Stroke(width = if (ring == 3) 2.1f else 1.3f),
        )
    }
    repeat(n) { i ->
        val angle = -PI / 2.0 + i * 2.0 * PI / n
        drawLine(
            color = gridColor,
            start = Offset(cx, cy),
            end = Offset(
                cx + cos(angle).toFloat() * maxR,
                cy + sin(angle).toFloat() * maxR,
            ),
            strokeWidth = 1.15f,
        )
    }
}

private fun DrawScope.drawFilledPolygon(
    cx: Float,
    cy: Float,
    maxR: Float,
    n: Int,
    scores: FloatArray,
    readyState: Boolean,
) {
    val points = Array(n) { i ->
        val angle = -PI / 2.0 + i * 2.0 * PI / n
        val r = maxR * (scores[i].coerceIn(0f, 10f) / 10f)
        Offset(cx + cos(angle).toFloat() * r, cy + sin(angle).toFloat() * r)
    }

    val path = Path().apply {
        moveTo(points[0].x, points[0].y)
        for (i in 1 until n) lineTo(points[i].x, points[i].y)
        close()
    }

    drawPath(
        path = path,
        brush = Brush.radialGradient(
            colors = listOf(
                Color(0xFF42E5C2).copy(alpha = if (readyState) 0.40f else 0.16f),
                Color(0xFF7C6CFF).copy(alpha = if (readyState) 0.24f else 0.08f),
                Color.Transparent,
            ),
            center = Offset(cx, cy),
            radius = maxR,
        ),
    )
    drawPath(
        path = path,
        color = Color(0xFF8ED8F8).copy(alpha = if (readyState) 0.9f else 0.4f),
        style = Stroke(width = 2.8f),
    )
}

private fun DrawScope.drawNodes(
    cx: Float,
    cy: Float,
    maxR: Float,
    n: Int,
    scores: FloatArray,
    readyState: Boolean,
) {
    repeat(n) { i ->
        val angle = -PI / 2.0 + i * 2.0 * PI / n
        val r = maxR * (scores[i].coerceIn(0f, 10f) / 10f)
        val dotX = cx + cos(angle).toFloat() * r
        val dotY = cy + sin(angle).toFloat() * r
        val outerAlpha = if (readyState) 1f else 0.45f
        drawCircle(
            color = WHEEL_DOMAINS[i].color.copy(alpha = outerAlpha),
            radius = 8f,
            center = Offset(dotX, dotY),
        )
        drawCircle(
            color = Color.White.copy(alpha = 0.72f * outerAlpha),
            radius = 3f,
            center = Offset(dotX, dotY),
        )
    }
}

private fun DrawScope.drawLabels(
    cx: Float,
    cy: Float,
    maxR: Float,
    n: Int,
    scores: FloatArray,
    readyState: Boolean,
) {
    drawIntoCanvas { canvas ->
        val labelPaint = android.graphics.Paint(android.graphics.Paint.ANTI_ALIAS_FLAG).apply {
            color = android.graphics.Color.argb(
                if (readyState) 232 else 168,
                233,
                242,
                247,
            )
            textSize = size.width * 0.028f
            textAlign = android.graphics.Paint.Align.CENTER
            isFakeBoldText = false
        }
        val scorePaint = android.graphics.Paint(android.graphics.Paint.ANTI_ALIAS_FLAG).apply {
            color = android.graphics.Color.argb(
                if (readyState) 194 else 130,
                142,
                216,
                248,
            )
            textSize = size.width * 0.022f
            textAlign = android.graphics.Paint.Align.CENTER
        }

        val labelR = maxR * 1.06f
        repeat(n) { i ->
            val angle = -PI / 2.0 + i * 2.0 * PI / n
            val lx = cx + cos(angle).toFloat() * labelR
            val ly = cy + sin(angle).toFloat() * labelR
            val lineH = labelPaint.textSize
            canvas.nativeCanvas.drawText(
                WHEEL_DOMAINS[i].label,
                lx,
                ly,
                labelPaint,
            )
            canvas.nativeCanvas.drawText(
                "${"%.1f".format(scores[i])}",
                lx,
                ly + lineH * 1.05f,
                scorePaint,
            )
        }
    }
}

private fun fetchWheelScores(baseHttpUrl: String): WheelUiModel {
    val today = LocalDate.now().toString()
    return try {
        val client = OkHttpClient.Builder()
            .connectTimeout(5, TimeUnit.SECONDS)
            .readTimeout(10, TimeUnit.SECONDS)
            .build()

        val url = "${baseHttpUrl.removeSuffix("/")}/balance/wheel?date=$today"
        val request = ServerEndpointResolver.attachAuth(
            Request.Builder().url(url),
            url,
        )
            .get()
            .build()

        val body = client.newCall(request).execute().use { resp ->
            if (!resp.isSuccessful) {
                return WheelUiModel(
                    state = WheelLoadState.ERROR,
                    scores = FloatArray(WHEEL_DOMAINS.size) { 0f },
                    helperText = "Колесо баланса временно недоступно.",
                )
            }
            resp.body?.string()
        } ?: return WheelUiModel(
            state = WheelLoadState.ERROR,
            scores = FloatArray(WHEEL_DOMAINS.size) { 0f },
            helperText = "Колесо баланса не вернуло данные.",
        )

        val json = JSONObject(body)
        if (!json.optBoolean("has_data", false)) {
            return WheelUiModel(
                state = WheelLoadState.EMPTY,
                scores = FloatArray(WHEEL_DOMAINS.size) { 0f },
                helperText = json.optString("empty_reason")
                    .takeIf { it.isNotBlank() }
                    ?: "Недостаточно осмысленных записей за сегодня.",
            )
        }
        val list = json.getJSONArray("domains")
        val map = mutableMapOf<String, Float>()
        for (j in 0 until list.length()) {
            val obj = list.getJSONObject(j)
            map[obj.getString("domain")] = obj.getDouble("score").toFloat()
        }
        WheelUiModel(
            state = WheelLoadState.READY,
            scores = FloatArray(WHEEL_DOMAINS.size) { i -> map[WHEEL_DOMAINS[i].key] ?: 0f },
            helperText = null,
        )
    } catch (e: Exception) {
        android.util.Log.w("BalanceWheel", "fetch failed: ${e.message}")
        WheelUiModel(
            state = WheelLoadState.ERROR,
            scores = FloatArray(WHEEL_DOMAINS.size) { 0f },
            helperText = "Не удалось загрузить колесо баланса.",
        )
    }
}
