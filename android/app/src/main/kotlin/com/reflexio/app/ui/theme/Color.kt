package com.reflexio.app.ui.theme

import androidx.compose.ui.graphics.Color

// ПОЧЕМУ эта палитра: ParticleFieldVisualizer уже использует тёмный фон (0xFF0A0E1A)
// с яркими свечениями. Дизайн "Digital Memory" — тёмная база + акценты.

// === Dark theme — основной для Reflexio ===
val DarkPrimary = Color(0xFF8ED8F8)              // Ледяной cyan
val DarkOnPrimary = Color(0xFFFFFFFF)
val DarkPrimaryContainer = Color(0xFF143647)
val DarkOnPrimaryContainer = Color(0xFFD5F5FF)

val DarkSecondary = Color(0xFF42E5C2)             // Живой mint
val DarkOnSecondary = Color(0xFF06271F)
val DarkSecondaryContainer = Color(0xFF113E35)
val DarkOnSecondaryContainer = Color(0xFFC5FFF1)

val DarkTertiary = Color(0xFFFF9B6A)              // Тёплый ember
val DarkOnTertiary = Color(0xFF3A1400)
val DarkTertiaryContainer = Color(0xFF5A2410)
val DarkOnTertiaryContainer = Color(0xFFFFDBC8)

val DarkBackground = Color(0xFF071018)
val DarkOnBackground = Color(0xFFE9F2F7)
val DarkSurface = Color(0xFF0E1922)
val DarkOnSurface = Color(0xFFE9F2F7)
val DarkSurfaceVariant = Color(0xFF162634)
val DarkOnSurfaceVariant = Color(0xFF9FB2BE)

val DarkError = Color(0xFFFF7A6A)
val DarkOnError = Color(0xFF690000)
val DarkErrorContainer = Color(0xFF93000A)
val DarkOnErrorContainer = Color(0xFFFFDAD6)

val DarkOutline = Color(0xFF314555)

// === Light theme — fallback ===
val LightPrimary = Color(0xFF006A8E)
val LightOnPrimary = Color(0xFFFFFFFF)
val LightPrimaryContainer = Color(0xFFCBEFFF)
val LightOnPrimaryContainer = Color(0xFF001E2A)

val LightSecondary = Color(0xFF006C57)
val LightOnSecondary = Color(0xFFFFFFFF)
val LightSecondaryContainer = Color(0xFF96F8DE)
val LightOnSecondaryContainer = Color(0xFF002019)

val LightTertiary = Color(0xFF9B4320)
val LightOnTertiary = Color(0xFFFFFFFF)
val LightTertiaryContainer = Color(0xFFFFDBCF)
val LightOnTertiaryContainer = Color(0xFF351000)

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
