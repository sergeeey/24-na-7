package com.reflexio.app.ui

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.animation.Crossfade
import androidx.compose.animation.core.tween
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.DateRange
import androidx.compose.material.icons.filled.Home
import androidx.compose.material.icons.filled.Insights
import androidx.compose.material.icons.filled.RecordVoiceOver
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FilledTonalButton
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.runtime.Composable
import androidx.compose.runtime.State
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.unit.dp
import androidx.core.content.ContextCompat
import com.reflexio.app.BuildConfig
import com.reflexio.app.data.db.RecordingDatabase
import com.reflexio.app.domain.services.AudioRecordingService
import com.reflexio.app.ui.components.BalanceWheelVisualizer
import com.reflexio.app.ui.components.RecordingFab
import com.reflexio.app.ui.screens.AnalyticsScreen
import com.reflexio.app.ui.screens.DailySummaryScreen
import com.reflexio.app.ui.screens.VoiceEnrollmentScreen
import com.reflexio.app.ui.screens.SplashScreen
import com.reflexio.app.ui.theme.ReflexioTheme

// ПОЧЕМУ enum а не sealed class: фиксированный набор экранов, sealed class — overkill
private enum class Screen(val title: String, val icon: ImageVector) {
    HOME("Запись", Icons.Default.Home),
    DIGEST("Итог дня", Icons.Default.DateRange),
    ANALYTICS("Аналитика", Icons.Default.Insights),
    VOICE("Голос", Icons.Default.RecordVoiceOver),
}

class MainActivity : ComponentActivity() {

    private val hasRecordingPermissionState = mutableStateOf(false)

    private val permissionLauncher = registerForActivityResult(
        ActivityResultContracts.RequestMultiplePermissions()
    ) { _ ->
        hasRecordingPermissionState.value = hasRequiredPermissions()
        if (hasRequiredPermissions()) startRecordingService()
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        try {
            onCreateImpl()
        } catch (e: Throwable) {
            android.util.Log.e("MainActivity", "onCreate failed", e)
            setContent {
                ReflexioTheme {
                    Text(
                        text = "Ошибка запуска: ${e.message}\n\n${e.javaClass.simpleName}",
                        modifier = Modifier.padding(16.dp)
                    )
                }
            }
        }
    }

    private fun onCreateImpl() {
        // Проверяем что Room DB инициализируется без ошибок (AudioRecordingService её использует)
        try {
            RecordingDatabase.getInstance(applicationContext)
        } catch (e: Exception) {
            android.util.Log.e("MainActivity", "Database init failed", e)
            setContent {
                ReflexioTheme {
                    Text(
                        text = "Ошибка БД: ${e.message}",
                        modifier = Modifier.padding(16.dp)
                    )
                }
            }
            return
        }
        hasRecordingPermissionState.value = hasRequiredPermissions()
        setContent {
            ReflexioTheme {
                RecordingApp(
                    hasRecordingPermission = hasRecordingPermissionState,
                    onRequestPermission = { permissionLauncher.launch(getRequiredPermissions()) },
                    onStartRecording = { startRecordingService() },
                    onStopRecording = {
                        stopService(Intent(this, AudioRecordingService::class.java))
                    }
                )
            }
        }
        if (hasRequiredPermissions()) {
            startRecordingService()
        } else {
            permissionLauncher.launch(getRequiredPermissions())
        }
    }

    private fun hasRequiredPermissions(): Boolean =
        getRequiredPermissions().all {
            ContextCompat.checkSelfPermission(this, it) == PackageManager.PERMISSION_GRANTED
        }

    private fun getRequiredPermissions(): Array<String> {
        val list = mutableListOf(Manifest.permission.RECORD_AUDIO)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            list.add(Manifest.permission.POST_NOTIFICATIONS)
        }
        return list.toTypedArray()
    }

    private fun startRecordingService() {
        val intent = Intent(this, AudioRecordingService::class.java)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            startForegroundService(intent)
        } else {
            startService(intent)
        }
    }
}

// ──────────────────────────────────────────────
// Root Composable — Scaffold + NavigationBar
// ──────────────────────────────────────────────

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun RecordingApp(
    hasRecordingPermission: State<Boolean>,
    onRequestPermission: () -> Unit,
    onStartRecording: () -> Unit,
    onStopRecording: () -> Unit,
) {
    // ПОЧЕМУ showSplash через remember а не rememberSaveable: при повороте экрана
    // или process death мы ХОТИМ показать splash заново — это корректно для branding-экрана.
    var showSplash by remember { mutableStateOf(true) }

    if (showSplash) {
        SplashScreen(onSplashFinished = { showSplash = false })
        return
    }

    val hasPermission by hasRecordingPermission
    var recordingActive by remember(hasPermission) { mutableStateOf(hasPermission) }
    var selectedTab by rememberSaveable { mutableIntStateOf(0) }

    // ПОЧЕМУ isEmulator() а не BuildConfig.DEBUG: DEBUG=true и на телефоне и на эмуляторе.
    // 10.0.2.2 работает ТОЛЬКО в эмуляторе. На телефоне с adb reverse нужен localhost.
    val baseHttpUrl = remember {
        val isEmu = android.os.Build.FINGERPRINT.contains("generic")
                || android.os.Build.MODEL.contains("sdk")
                || android.os.Build.MODEL.contains("Android SDK")
        val ws = if (isEmu) BuildConfig.SERVER_WS_URL else BuildConfig.SERVER_WS_URL_DEVICE
        ws.replace("ws://", "http://").replace("wss://", "https://")
    }

    val screens = Screen.entries

    Scaffold(
        topBar = {
            TopAppBar(
                title = {
                    Text(
                        text = screens[selectedTab].title,
                        style = MaterialTheme.typography.titleLarge
                    )
                },
                colors = TopAppBarDefaults.topAppBarColors(
                    containerColor = MaterialTheme.colorScheme.background,
                    titleContentColor = MaterialTheme.colorScheme.onBackground,
                ),
            )
        },
        bottomBar = {
            NavigationBar(
                containerColor = MaterialTheme.colorScheme.surface.copy(alpha = 0.95f),
            ) {
                screens.forEachIndexed { index, screen ->
                    NavigationBarItem(
                        selected = selectedTab == index,
                        onClick = { selectedTab = index },
                        icon = { Icon(screen.icon, contentDescription = screen.title) },
                        label = { Text(screen.title) },
                    )
                }
            }
        },
        containerColor = MaterialTheme.colorScheme.background,
    ) { padding ->
        // ПОЧЕМУ Crossfade а не AnimatedContent: Crossfade проще (только fade in/out),
        // не требует AnimatedContentScope. Для 3 табов без shared element transitions — идеально.
        // 300ms — быстрый но заметный переход (< 200ms резко, > 500ms тормозно).
        Crossfade(
            targetState = selectedTab,
            animationSpec = tween(300),
            label = "tabCrossfade",
        ) { tab ->
            when (tab) {
                0 -> HomeScreen(
                    hasPermission = hasPermission,
                    recordingActive = recordingActive,
                    baseHttpUrl = baseHttpUrl,
                    onRequestPermission = onRequestPermission,
                    onToggleRecording = {
                        if (recordingActive) {
                            onStopRecording(); recordingActive = false
                        } else {
                            onStartRecording(); recordingActive = true
                        }
                    },
                    modifier = Modifier.padding(padding),
                )
                1 -> DailySummaryScreen(
                    onBack = { selectedTab = 0 },
                    baseHttpUrl = baseHttpUrl,
                    modifier = Modifier.padding(padding),
                )
                2 -> AnalyticsScreen(
                    onBack = { selectedTab = 0 },
                    onOpenDailySummary = { selectedTab = 1 },
                    modifier = Modifier.padding(padding),
                )
                3 -> VoiceEnrollmentScreen(
                    baseHttpUrl = baseHttpUrl,
                    modifier = Modifier.padding(padding),
                )
            }
        }
    }
}

// ──────────────────────────────────────────────
// Home Screen — колесо баланса + кнопка записи
// ──────────────────────────────────────────────

/**
 * Главный экран переработан: вместо списка записей — Колесо Баланса.
 *
 * ПОЧЕМУ убрали RecordingListScreen: пользователь не хотел видеть поток записей
 * на главном экране. Список — техническая деталь, не ценность. Ценность —
 * визуализация того, как распределяется внимание по жизненным сферам.
 *
 * ПОЧЕМУ убрали AudioSpectrumAnalyzer/ParticleFieldVisualizer: они дублировали
 * анимацию. BalanceWheelVisualizer сам анимируется при записи (3D tilt + вращение).
 *
 * Layout: WelcomeBlock (компактный) → колесо (weight(1f) = занимает всё пространство)
 * → статус + FAB внизу. Колесо всегда видно, при записи — оживает.
 */
@Composable
private fun HomeScreen(
    hasPermission: Boolean,
    recordingActive: Boolean,
    baseHttpUrl: String,
    onRequestPermission: () -> Unit,
    onToggleRecording: () -> Unit,
    modifier: Modifier = Modifier,
) {
    Column(
        modifier = modifier
            .fillMaxSize()
            .padding(horizontal = 16.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Spacer(modifier = Modifier.height(8.dp))
        WelcomeBlock()
        Spacer(modifier = Modifier.height(12.dp))

        // Колесо баланса — главный визуальный элемент
        // ПОЧЕМУ weight(1f): занимает всё доступное пространство между
        // WelcomeBlock сверху и кнопкой снизу. Responsive — работает на любом экране.
        BalanceWheelVisualizer(
            baseHttpUrl = baseHttpUrl,
            isRecording = recordingActive,
            modifier = Modifier
                .fillMaxWidth()
                .weight(1f),
        )

        Spacer(modifier = Modifier.height(8.dp))

        if (!hasPermission) {
            Text(
                text = "Для записи нужен доступ к микрофону",
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            Spacer(modifier = Modifier.height(8.dp))
            FilledTonalButton(onClick = onRequestPermission) {
                Text("Разрешить доступ к микрофону")
            }
        } else {
            Text(
                text = if (recordingActive) "Слушаю..." else "Нажмите для записи",
                style = MaterialTheme.typography.titleMedium,
                color = if (recordingActive)
                    MaterialTheme.colorScheme.secondary
                else
                    MaterialTheme.colorScheme.onSurfaceVariant,
            )
            Spacer(modifier = Modifier.height(12.dp))
            RecordingFab(
                isRecording = recordingActive,
                onClick = onToggleRecording,
            )
        }
        Spacer(modifier = Modifier.height(16.dp))
    }
}

// ──────────────────────────────────────────────
// Welcome Block
// ──────────────────────────────────────────────

@Composable
private fun WelcomeBlock() {
    val greeting = remember {
        val hour = java.util.Calendar.getInstance().get(java.util.Calendar.HOUR_OF_DAY)
        when {
            hour in 5..11 -> "Доброе утро"
            hour in 12..16 -> "Добрый день"
            else -> "Добрый вечер"
        }
    }
    Card(
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(
            containerColor = MaterialTheme.colorScheme.primaryContainer
        ),
        shape = MaterialTheme.shapes.medium,
    ) {
        Column(modifier = Modifier.padding(horizontal = 16.dp, vertical = 12.dp)) {
            Text(
                text = greeting,
                style = MaterialTheme.typography.titleLarge,
                color = MaterialTheme.colorScheme.onPrimaryContainer,
            )
            Spacer(modifier = Modifier.height(2.dp))
            Text(
                text = "Колесо баланса — как распределяется твой день",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onPrimaryContainer.copy(alpha = 0.75f),
            )
        }
    }
}
