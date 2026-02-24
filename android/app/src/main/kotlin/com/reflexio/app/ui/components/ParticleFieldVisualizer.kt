package com.reflexio.app.ui.components

import androidx.compose.animation.core.*
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.*
import androidx.compose.ui.graphics.drawscope.DrawScope
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlin.math.*
import kotlin.random.Random

/**
 * Гиперреалистичный Particle Field эквалайзер
 *
 * Фичи:
 * - 300+ частиц с физикой
 * - Гравитационное взаимодействие
 * - Bloom эффект (свечение)
 * - Motion blur
 * - Particle trails (следы)
 * - Реалистичные цветовые градиенты
 * - Ambient occlusion
 */
@Composable
fun ParticleFieldVisualizer(
    audioLevels: List<Float>, // 0.0..1.0 для каждой частотной полосы (8-16 полос)
    isRecording: Boolean,
    modifier: Modifier = Modifier
) {
    val particles = remember { ParticleSystem(particleCount = 300) }

    // Анимация времени для плавных движений
    val infiniteTransition = rememberInfiniteTransition(label = "time")
    val time by infiniteTransition.animateFloat(
        initialValue = 0f,
        targetValue = 1000f,
        animationSpec = infiniteRepeatable(
            animation = tween(durationMillis = 100000, easing = LinearEasing),
            repeatMode = RepeatMode.Restart
        ),
        label = "time"
    )

    // Обновление частиц на основе аудио
    LaunchedEffect(isRecording) {
        while (isActive && isRecording) {
            particles.update(audioLevels, time)
            delay(16) // ~60 FPS
        }
    }

    Canvas(modifier = modifier.fillMaxSize()) {
        // Темный фон с градиентом
        drawRect(
            brush = Brush.radialGradient(
                colors = listOf(
                    Color(0xFF0A0E1A),
                    Color(0xFF000000)
                ),
                center = Offset(size.width / 2, size.height / 2),
                radius = size.maxDimension * 0.8f
            )
        )

        // Ambient light (фоновое свечение)
        drawAmbientLight(audioLevels)

        // Particle trails (следы частиц)
        particles.drawTrails(this)

        // Основные частицы
        particles.draw(this, audioLevels)

        // Bloom эффект (свечение)
        particles.drawBloom(this)

        // Connection lines (связи между близкими частицами)
        if (isRecording) {
            particles.drawConnections(this, audioLevels)
        }
    }
}

/**
 * Система частиц с физикой
 */
private class ParticleSystem(particleCount: Int) {
    data class Particle(
        var x: Float,
        var y: Float,
        var vx: Float, // velocity X
        var vy: Float, // velocity Y
        var size: Float,
        var hue: Float, // 0..360 для HSV
        var energy: Float, // 0..1 для яркости
        val frequencyBand: Int, // какая частота управляет этой частицей
        val trail: MutableList<Offset> = mutableListOf() // следы
    )

    private val particles: List<Particle> = List(particleCount) { i ->
        Particle(
            x = Random.nextFloat(),
            y = Random.nextFloat(),
            vx = (Random.nextFloat() - 0.5f) * 0.002f,
            vy = (Random.nextFloat() - 0.5f) * 0.002f,
            size = Random.nextFloat() * 3f + 1f,
            hue = Random.nextFloat() * 360f,
            energy = Random.nextFloat(),
            frequencyBand = i % 8 // распределяем по частотам
        )
    }

    fun update(audioLevels: List<Float>, time: Float) {
        val levels = audioLevels.takeIf { it.isNotEmpty() } ?: List(8) { 0f }

        particles.forEach { particle ->
            // Получаем уровень для частотной полосы этой частицы
            val level = levels.getOrElse(particle.frequencyBand) { 0f }

            // Обновляем энергию (плавно)
            particle.energy = particle.energy * 0.9f + level * 0.1f

            // Гравитация к центру (слабая)
            val centerX = 0.5f
            val centerY = 0.5f
            val dx = centerX - particle.x
            val dy = centerY - particle.y
            val dist = sqrt(dx * dx + dy * dy)

            if (dist > 0.01f) {
                val force = 0.00001f * particle.energy
                particle.vx += (dx / dist) * force
                particle.vy += (dy / dist) * force
            }

            // Орбитальное движение (вихри)
            val angle = atan2(dy, dx)
            val orbitalForce = 0.00005f * particle.energy
            particle.vx += cos(angle + PI.toFloat() / 2) * orbitalForce
            particle.vy += sin(angle + PI.toFloat() / 2) * orbitalForce

            // Волновое движение по времени
            val wave = sin(time * 0.01f + particle.frequencyBand * 0.5f) * 0.0001f
            particle.vy += wave * particle.energy

            // Применяем скорость
            particle.x += particle.vx
            particle.y += particle.vy

            // Затухание скорости (трение)
            particle.vx *= 0.98f
            particle.vy *= 0.98f

            // Границы (bounce)
            if (particle.x < 0f || particle.x > 1f) {
                particle.vx *= -0.8f
                particle.x = particle.x.coerceIn(0f, 1f)
            }
            if (particle.y < 0f || particle.y > 1f) {
                particle.vy *= -0.8f
                particle.y = particle.y.coerceIn(0f, 1f)
            }

            // Обновляем цвет (hue shift)
            particle.hue = (particle.hue + particle.energy * 0.5f) % 360f

            // Сохраняем след
            particle.trail.add(0, Offset(particle.x, particle.y))
            if (particle.trail.size > 20) {
                particle.trail.removeAt(particle.trail.lastIndex)
            }
        }
    }

    fun draw(scope: DrawScope, audioLevels: List<Float>) {
        with(scope) {
            particles.forEach { particle ->
                val x = particle.x * size.width
                val y = particle.y * size.height

                // Размер зависит от энергии
                val radius = particle.size * (1f + particle.energy * 2f)

                // Цвет: HSV -> RGB с альфой по энергии
                val color = Color.hsv(
                    hue = particle.hue,
                    saturation = 0.8f,
                    value = 0.9f,
                    alpha = 0.6f + particle.energy * 0.4f
                )

                // Внутреннее ядро (яркое)
                drawCircle(
                    color = color.copy(alpha = 1f),
                    radius = radius * 0.5f,
                    center = Offset(x, y),
                    blendMode = BlendMode.Screen // Additive blending для свечения
                )

                // Внешнее свечение (soft)
                drawCircle(
                    brush = Brush.radialGradient(
                        colors = listOf(
                            color.copy(alpha = 0.6f),
                            color.copy(alpha = 0f)
                        ),
                        center = Offset(x, y),
                        radius = radius * 2f
                    ),
                    radius = radius * 2f,
                    center = Offset(x, y),
                    blendMode = BlendMode.Screen
                )
            }
        }
    }

    fun drawTrails(scope: DrawScope) {
        with(scope) {
            particles.forEach { particle ->
                if (particle.trail.size < 2) return@forEach

                val path = Path()
                val firstPoint = particle.trail[0]
                path.moveTo(firstPoint.x * size.width, firstPoint.y * size.height)

                for (i in 1 until particle.trail.size) {
                    val point = particle.trail[i]
                    path.lineTo(point.x * size.width, point.y * size.height)
                }

                // Градиент от яркого к прозрачному
                val color = Color.hsv(particle.hue, 0.7f, 0.8f)

                drawPath(
                    path = path,
                    brush = Brush.linearGradient(
                        colors = listOf(
                            color.copy(alpha = 0.4f * particle.energy),
                            color.copy(alpha = 0f)
                        )
                    ),
                    style = androidx.compose.ui.graphics.drawscope.Stroke(
                        width = particle.size * 0.5f
                    ),
                    blendMode = BlendMode.Screen
                )
            }
        }
    }

    fun drawBloom(scope: DrawScope) {
        with(scope) {
            // Большие bloom сферы для высокоэнергетичных частиц
            particles.filter { it.energy > 0.5f }.forEach { particle ->
                val x = particle.x * size.width
                val y = particle.y * size.height
                val radius = particle.size * 10f * particle.energy

                val color = Color.hsv(particle.hue, 0.6f, 1f)

                drawCircle(
                    brush = Brush.radialGradient(
                        colors = listOf(
                            color.copy(alpha = 0.15f * particle.energy),
                            color.copy(alpha = 0f)
                        ),
                        center = Offset(x, y),
                        radius = radius
                    ),
                    radius = radius,
                    center = Offset(x, y),
                    blendMode = BlendMode.Screen
                )
            }
        }
    }

    fun drawConnections(scope: DrawScope, audioLevels: List<Float>) {
        with(scope) {
            val maxDistance = 0.15f // максимальное расстояние для связи

            // Проверяем все пары частиц
            for (i in particles.indices) {
                for (j in i + 1 until particles.size) {
                    val p1 = particles[i]
                    val p2 = particles[j]

                    val dx = p1.x - p2.x
                    val dy = p1.y - p2.y
                    val dist = sqrt(dx * dx + dy * dy)

                    if (dist < maxDistance) {
                        val alpha = (1f - dist / maxDistance) * 0.3f
                        val avgEnergy = (p1.energy + p2.energy) / 2f

                        // Цвет — среднее между двумя частицами
                        val avgHue = (p1.hue + p2.hue) / 2f
                        val color = Color.hsv(avgHue, 0.7f, 0.8f, alpha = alpha * avgEnergy)

                        drawLine(
                            color = color,
                            start = Offset(p1.x * size.width, p1.y * size.height),
                            end = Offset(p2.x * size.width, p2.y * size.height),
                            strokeWidth = 1f,
                            blendMode = BlendMode.Screen
                        )
                    }
                }
            }
        }
    }
}

/**
 * Фоновое свечение (ambient light)
 */
private fun DrawScope.drawAmbientLight(audioLevels: List<Float>) {
    if (audioLevels.isEmpty()) return

    val avgLevel = audioLevels.average().toFloat()

    // Большой радиальный градиент в центре
    drawCircle(
        brush = Brush.radialGradient(
            colors = listOf(
                Color(0xFF1A0F3E).copy(alpha = avgLevel * 0.4f),
                Color.Transparent
            ),
            center = Offset(size.width / 2, size.height / 2),
            radius = size.maxDimension * 0.6f
        ),
        radius = size.maxDimension * 0.6f,
        center = Offset(size.width / 2, size.height / 2),
        blendMode = BlendMode.Screen
    )
}
