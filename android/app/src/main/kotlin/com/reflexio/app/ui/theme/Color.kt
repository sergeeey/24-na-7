package com.reflexio.app.ui.theme

import androidx.compose.ui.graphics.Color

// ПОЧЕМУ эта палитра: ParticleFieldVisualizer уже использует тёмный фон (0xFF0A0E1A)
// с яркими свечениями. Дизайн "Digital Memory" — тёмная база + акценты.

// === Dark theme — основной для Reflexio ===
val DarkPrimary = Color(0xFF7C6CFF)              // Мягкий индиго
val DarkOnPrimary = Color(0xFFFFFFFF)
val DarkPrimaryContainer = Color(0xFF2D2566)
val DarkOnPrimaryContainer = Color(0xFFCDC4FF)

val DarkSecondary = Color(0xFF00E5CC)             // Тёплый teal
val DarkOnSecondary = Color(0xFF003730)
val DarkSecondaryContainer = Color(0xFF004D44)
val DarkOnSecondaryContainer = Color(0xFF7CF8E4)

val DarkTertiary = Color(0xFFFFB74D)              // Тёплый amber для акцентов
val DarkOnTertiary = Color(0xFF462A00)
val DarkTertiaryContainer = Color(0xFF633F00)
val DarkOnTertiaryContainer = Color(0xFFFFDDB3)

val DarkBackground = Color(0xFF0D1117)
val DarkOnBackground = Color(0xFFE6EDF3)
val DarkSurface = Color(0xFF161B22)
val DarkOnSurface = Color(0xFFE6EDF3)
val DarkSurfaceVariant = Color(0xFF1C2333)
val DarkOnSurfaceVariant = Color(0xFFB0BAC5)

val DarkError = Color(0xFFFF6B6B)
val DarkOnError = Color(0xFF690000)
val DarkErrorContainer = Color(0xFF93000A)
val DarkOnErrorContainer = Color(0xFFFFDAD6)

val DarkOutline = Color(0xFF3D4450)

// === Light theme — fallback ===
val LightPrimary = Color(0xFF5B4FC4)
val LightOnPrimary = Color(0xFFFFFFFF)
val LightPrimaryContainer = Color(0xFFE8E0FF)
val LightOnPrimaryContainer = Color(0xFF1A0066)

val LightSecondary = Color(0xFF00A389)
val LightOnSecondary = Color(0xFFFFFFFF)
val LightSecondaryContainer = Color(0xFFB2F5E8)
val LightOnSecondaryContainer = Color(0xFF002E25)

val LightTertiary = Color(0xFFFF8F00)
val LightOnTertiary = Color(0xFFFFFFFF)
val LightTertiaryContainer = Color(0xFFFFE0B2)
val LightOnTertiaryContainer = Color(0xFF2E1500)

val LightBackground = Color(0xFFF8F9FA)
val LightOnBackground = Color(0xFF1B1B1F)
val LightSurface = Color(0xFFFFFFFF)
val LightOnSurface = Color(0xFF1B1B1F)
val LightSurfaceVariant = Color(0xFFE7E8EC)
val LightOnSurfaceVariant = Color(0xFF49454F)

val LightError = Color(0xFFBA1A1A)
val LightOnError = Color(0xFFFFFFFF)
val LightErrorContainer = Color(0xFFFFDAD6)
val LightOnErrorContainer = Color(0xFF410002)

val LightOutline = Color(0xFF79747E)
