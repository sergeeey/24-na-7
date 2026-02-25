package com.reflexio.app.ui.components

import androidx.compose.animation.core.LinearEasing
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.drawscope.DrawScope
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.drawscope.drawIntoCanvas
import androidx.compose.ui.graphics.graphicsLayer
import com.reflexio.app.BuildConfig
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import okhttp3.OkHttpClient
import okhttp3.Request
import org.json.JSONObject
import java.time.LocalDate
import java.util.concurrent.TimeUnit
import kotlin.math.PI
import kotlin.math.cos
import kotlin.math.min
import kotlin.math.sin

// ──────────────────────────────────────────────
// Домены колеса баланса (8 жизненных сфер)
// ──────────────────────────────────────────────

private data class WheelDomain(
    val key: String,
    val label: String,
    val color: Color,
)

private val WHEEL_DOMAINS = listOf(
    WheelDomain("work",       "Работа",     Color(0xFF7C6CFF)),
    WheelDomain("health",     "Здоровье",   Color(0xFF00E5CC)),
    WheelDomain("family",     "Семья",      Color(0xFFFFB74D)),
    WheelDomain("finance",    "Финансы",    Color(0xFF4CAF50)),
    WheelDomain("psychology", "Психология", Color(0xFFE040FB)),
    WheelDomain("relations",  "Отношения",  Color(0xFFFF6B6B)),
    WheelDomain("growth",     "Рост",       Color(0xFF29B6F6)),
    WheelDomain("leisure",    "Отдых",      Color(0xFFFFF176)),
)

// ──────────────────────────────────────────────
// Composable
// ──────────────────────────────────────────────

/**
 * Колесо баланса — радарный 8-секторный график.
 *
 * ПОЧЕМУ graphicsLayer rotationX: имитирует 3D-наклон без дорогого 3D-рендеринга.
 * При rotationX=22° круг превращается в эллипс — визуально как колесо под углом.
 *
 * ПОЧЕМУ rotationZ анимируется только при записи: когда запись идёт, колесо
 * медленно вращается (25 сек/оборот), давая ощущение "живого" процесса.
 * В паузе — статично, можно читать подписи.
 *
 * ПОЧЕМУ OkHttp напрямую: уже в зависимостях, Retrofit ради одного endpoint — overkill.
 * ПОЧЕМУ scores по умолчанию 5f: показывает нейтральный круг пока данные не пришли.
 */
@Composable
fun BalanceWheelVisualizer(
    baseHttpUrl: String,
    isRecording: Boolean,
    modifier: Modifier = Modifier,
) {
    val scope = rememberCoroutineScope()

    // FloatArray(8) вместо List<Float> — нет boxing, прямой доступ по индексу
    var scores by remember { mutableStateOf(FloatArray(8) { 5f }) }

    // Бесконечная анимация вращения вокруг оси Z
    val infiniteTransition = rememberInfiniteTransition(label = "wheelSpin")
    val spinZ by infiniteTransition.animateFloat(
        initialValue = 0f,
        targetValue = 360f,
        animationSpec = infiniteRepeatable(
            animation = tween(durationMillis = 25_000, easing = LinearEasing),
            repeatMode = RepeatMode.Restart,
        ),
        label = "spinZ",
    )

    // 3D наклон: появляется плавно при старте записи, исчезает при остановке
    val tiltX by animateFloatAsState(
        targetValue = if (isRecording) 22f else 0f,
        animationSpec = tween(durationMillis = 900),
        label = "tiltX",
    )

    // Прозрачность: чуть ярче во время записи
    val alpha by animateFloatAsState(
        targetValue = if (isRecording) 1f else 0.75f,
        animationSpec = tween(600),
        label = "alpha",
    )

    // Перезагружаем данные при каждом изменении состояния записи
    // ПОЧЕМУ LaunchedEffect(isRecording): при остановке записи обновляем колесо
    // с новыми данными — только что записанное уже обработано сервером.
    LaunchedEffect(isRecording) {
        scope.launch(Dispatchers.IO) {
            val fetched = fetchWheelScores(baseHttpUrl)
            withContext(Dispatchers.Main) { scores = fetched }
        }
    }

    Canvas(
        modifier = modifier
            .fillMaxSize()
            .graphicsLayer {
                this.rotationX = tiltX
                this.rotationZ = if (isRecording) spinZ else 0f
                this.alpha = alpha
                // cameraDistance предотвращает "схлопывание" при больших rotationX
                this.cameraDistance = 8f * density
            },
    ) {
        val cx = size.width / 2f
        val cy = size.height / 2f
        // 32% от минимального размера — остаток занимают подписи снаружи
        val maxR = min(size.width, size.height) * 0.32f
        val n = WHEEL_DOMAINS.size

        drawGrid(cx, cy, maxR, n)
        drawFilledPolygon(cx, cy, maxR, n, scores)
        drawNodes(cx, cy, maxR, n, scores)
        drawLabels(cx, cy, maxR, n, scores)
    }
}

// ──────────────────────────────────────────────
// Canvas drawing helpers
// ──────────────────────────────────────────────

private fun DrawScope.drawGrid(cx: Float, cy: Float, maxR: Float, n: Int) {
    val gridColor = Color.White.copy(alpha = 0.14f)
    // 4 концентрических кольца
    repeat(4) { ring ->
        val r = maxR * (ring + 1).toFloat() / 4f
        drawCircle(color = gridColor, radius = r, center = Offset(cx, cy), style = Stroke(1.5f))
    }
    // Спицы
    repeat(n) { i ->
        val angle = -PI / 2.0 + i * 2.0 * PI / n
        drawLine(
            color = gridColor,
            start = Offset(cx, cy),
            end = Offset(
                cx + cos(angle).toFloat() * maxR,
                cy + sin(angle).toFloat() * maxR,
            ),
            strokeWidth = 1f,
        )
    }
}

private fun DrawScope.drawFilledPolygon(
    cx: Float, cy: Float, maxR: Float, n: Int, scores: FloatArray,
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

    // Радиальный градиент: teal в центре, indigo к краям
    drawPath(
        path = path,
        brush = Brush.radialGradient(
            colors = listOf(
                Color(0xFF00E5CC).copy(alpha = 0.50f),
                Color(0xFF7C6CFF).copy(alpha = 0.28f),
            ),
            center = Offset(cx, cy),
            radius = maxR,
        ),
    )
    // Контур
    drawPath(
        path = path,
        color = Color(0xFF00E5CC).copy(alpha = 0.95f),
        style = Stroke(width = 2.5f),
    )
}

private fun DrawScope.drawNodes(
    cx: Float, cy: Float, maxR: Float, n: Int, scores: FloatArray,
) {
    repeat(n) { i ->
        val angle = -PI / 2.0 + i * 2.0 * PI / n
        val r = maxR * (scores[i].coerceIn(0f, 10f) / 10f)
        val dotX = cx + cos(angle).toFloat() * r
        val dotY = cy + sin(angle).toFloat() * r
        // Цветная точка домена
        drawCircle(
            color = WHEEL_DOMAINS[i].color,
            radius = 7f,
            center = Offset(dotX, dotY),
        )
        // Небольшое белое ядро для глубины
        drawCircle(
            color = Color.White.copy(alpha = 0.6f),
            radius = 2.5f,
            center = Offset(dotX, dotY),
        )
    }
}

private fun DrawScope.drawLabels(
    cx: Float, cy: Float, maxR: Float, n: Int, scores: FloatArray,
) {
    // Метки рисуем через nativeCanvas — Compose drawText недоступен в DrawScope
    drawIntoCanvas { canvas ->
        val labelPaint = android.graphics.Paint(android.graphics.Paint.ANTI_ALIAS_FLAG).apply {
            color = android.graphics.Color.argb(204, 230, 237, 243)  // ~0xCCE6EDF3
            textSize = size.width * 0.033f
            textAlign = android.graphics.Paint.Align.CENTER
            isFakeBoldText = false
        }
        val scorePaint = android.graphics.Paint(android.graphics.Paint.ANTI_ALIAS_FLAG).apply {
            color = android.graphics.Color.argb(153, 0, 229, 204) // teal, 60%
            textSize = size.width * 0.028f
            textAlign = android.graphics.Paint.Align.CENTER
        }

        // Метки на 115% от maxR
        val labelR = maxR * 1.18f
        repeat(n) { i ->
            val angle = -PI / 2.0 + i * 2.0 * PI / n
            val lx = cx + cos(angle).toFloat() * labelR
            val ly = cy + sin(angle).toFloat() * labelR
            val lineH = labelPaint.textSize
            // Название домена
            canvas.nativeCanvas.drawText(
                WHEEL_DOMAINS[i].label,
                lx,
                ly,
                labelPaint,
            )
            // Счёт под названием
            canvas.nativeCanvas.drawText(
                "${"%.1f".format(scores[i])}",
                lx,
                ly + lineH * 1.1f,
                scorePaint,
            )
        }
    }
}

// ──────────────────────────────────────────────
// HTTP — загрузка данных
// ──────────────────────────────────────────────

/**
 * GET /balance/wheel?date=today
 * Возвращает FloatArray(8) с очками в порядке WHEEL_DOMAINS.
 * При ошибке или отсутствии данных — 5f (нейтральный баланс).
 *
 * ПОЧЕМУ suspend нет: вызывается из launch(Dispatchers.IO), блокировать поток безопасно.
 * ПОЧЕМУ JSONObject (Android built-in): нет нужды в Gson/kotlinx.serialization ради одного парсинга.
 */
private fun fetchWheelScores(baseHttpUrl: String): FloatArray {
    val today = LocalDate.now().toString()
    return try {
        val client = OkHttpClient.Builder()
            .connectTimeout(5, TimeUnit.SECONDS)
            .readTimeout(10, TimeUnit.SECONDS)
            .build()

        val request = Request.Builder()
            .url("${baseHttpUrl.removeSuffix("/")}/balance/wheel?date=$today")
            .apply {
                if (BuildConfig.SERVER_API_KEY.isNotEmpty()) {
                    addHeader("Authorization", "Bearer ${BuildConfig.SERVER_API_KEY}")
                }
            }
            .get()
            .build()

        val body = client.newCall(request).execute().use { resp ->
            if (!resp.isSuccessful) return FloatArray(8) { 5f }
            resp.body?.string()
        } ?: return FloatArray(8) { 5f }

        val json = JSONObject(body)
        val list = json.getJSONArray("domains")
        val map = mutableMapOf<String, Float>()
        for (j in 0 until list.length()) {
            val obj = list.getJSONObject(j)
            map[obj.getString("domain")] = obj.getDouble("score").toFloat()
        }
        FloatArray(8) { i -> map[WHEEL_DOMAINS[i].key] ?: 5f }
    } catch (e: Exception) {
        android.util.Log.w("BalanceWheel", "fetch failed: ${e.message}")
        FloatArray(8) { 5f }
    }
}
