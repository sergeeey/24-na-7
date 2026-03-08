package com.reflexio.app.ui.components

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.BlendMode
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.drawscope.Stroke

/**
 * Атмосферный фон приложения.
 *
 * Это не "эффект ради эффекта": мягкие световые пятна и орбиты собирают экраны в одно
 * визуальное пространство, не отвлекая от основного контента.
 */
@Composable
fun AmbientBackdrop(modifier: Modifier = Modifier) {
    Canvas(modifier = modifier.fillMaxSize()) {
        drawRect(
            brush = Brush.verticalGradient(
                colors = listOf(
                    Color(0xFF050D14),
                    Color(0xFF071018),
                    Color(0xFF0A1621),
                ),
            ),
        )

        drawCircle(
            brush = Brush.radialGradient(
                colors = listOf(
                    Color(0xFF8ED8F8).copy(alpha = 0.18f),
                    Color.Transparent,
                ),
                center = Offset(size.width * 0.18f, size.height * 0.16f),
                radius = size.minDimension * 0.42f,
            ),
            radius = size.minDimension * 0.42f,
            center = Offset(size.width * 0.18f, size.height * 0.16f),
            blendMode = BlendMode.Screen,
        )

        drawCircle(
            brush = Brush.radialGradient(
                colors = listOf(
                    Color(0xFF42E5C2).copy(alpha = 0.14f),
                    Color.Transparent,
                ),
                center = Offset(size.width * 0.82f, size.height * 0.28f),
                radius = size.minDimension * 0.34f,
            ),
            radius = size.minDimension * 0.34f,
            center = Offset(size.width * 0.82f, size.height * 0.28f),
            blendMode = BlendMode.Screen,
        )

        drawCircle(
            brush = Brush.radialGradient(
                colors = listOf(
                    Color(0xFFFF9B6A).copy(alpha = 0.10f),
                    Color.Transparent,
                ),
                center = Offset(size.width * 0.54f, size.height * 0.72f),
                radius = size.minDimension * 0.28f,
            ),
            radius = size.minDimension * 0.28f,
            center = Offset(size.width * 0.54f, size.height * 0.72f),
            blendMode = BlendMode.Screen,
        )

        drawCircle(
            color = Color.White.copy(alpha = 0.05f),
            radius = size.minDimension * 0.34f,
            center = Offset(size.width * 0.78f, size.height * 0.82f),
            style = Stroke(width = 1.2f),
        )

        drawCircle(
            color = Color.White.copy(alpha = 0.035f),
            radius = size.minDimension * 0.52f,
            center = Offset(size.width * 0.22f, size.height * 0.72f),
            style = Stroke(width = 1.0f),
        )
    }
}
