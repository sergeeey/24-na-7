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
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.DateRange
import androidx.compose.material.icons.filled.Home
import androidx.compose.material.icons.filled.Insights
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
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.State
import androidx.compose.runtime.collectAsState
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
import androidx.compose.ui.zIndex
import androidx.core.content.ContextCompat
import com.reflexio.app.BuildConfig
import com.reflexio.app.data.db.RecordingDao
import com.reflexio.app.data.db.RecordingDatabase
import com.reflexio.app.data.model.Recording
import com.reflexio.app.domain.audio.AudioSpectrumAnalyzer
import com.reflexio.app.domain.services.AudioRecordingService
import com.reflexio.app.ui.components.ParticleFieldVisualizer
import com.reflexio.app.ui.screens.AnalyticsScreen
import com.reflexio.app.ui.screens.DailySummaryScreen
import com.reflexio.app.ui.screens.RecordingListScreen
import com.reflexio.app.ui.theme.ReflexioTheme

// ПОЧЕМУ enum а не sealed class: 3 фиксированных экрана, sealed class — overkill
private enum class Screen(val title: String, val icon: ImageVector) {
    HOME("Запись", Icons.Default.Home),
    DIGEST("Итог дня", Icons.Default.DateRange),
    ANALYTICS("Аналитика", Icons.Default.Insights),
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
        val dao = try {
            RecordingDatabase.getInstance(applicationContext).recordingDao()
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
                    recordingDao = dao,
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
    recordingDao: RecordingDao,
    hasRecordingPermission: State<Boolean>,
    onRequestPermission: () -> Unit,
    onStartRecording: () -> Unit,
    onStopRecording: () -> Unit
) {
    val hasPermission by hasRecordingPermission
    var recordingActive by remember(hasPermission) { mutableStateOf(hasPermission) }
    var recordings by remember { mutableStateOf<List<Recording>>(emptyList()) }
    var loadError by remember { mutableStateOf<String?>(null) }
    var selectedTab by rememberSaveable { mutableIntStateOf(0) }

    val baseHttpUrl = remember {
        val ws = if (BuildConfig.DEBUG) BuildConfig.SERVER_WS_URL else BuildConfig.SERVER_WS_URL_DEVICE
        ws.replace("ws://", "http://").replace("wss://", "https://")
    }

    // Audio spectrum analyzer
    val spectrumAnalyzer = remember { AudioSpectrumAnalyzer() }
    val audioLevels by spectrumAnalyzer.frequencyBands.collectAsState()

    DisposableEffect(recordingActive) {
        if (recordingActive) spectrumAnalyzer.start()
        onDispose { spectrumAnalyzer.stop() }
    }

    LaunchedEffect(Unit) {
        try {
            recordingDao.getAllRecordings().collect { recordings = it }
        } catch (e: Exception) {
            android.util.Log.e("RecordingApp", "getAllRecordings failed", e)
            loadError = e.message ?: e.javaClass.simpleName
        }
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
        // ПОЧЕМУ when вместо NavHost: 3 экрана, нет deep links, состояние хранится выше.
        // NavHost добавим когда экранов будет > 5 или нужен deep linking.
        when (selectedTab) {
            0 -> HomeScreen(
                hasPermission = hasPermission,
                recordingActive = recordingActive,
                recordings = recordings,
                loadError = loadError,
                audioLevels = audioLevels,
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
        }
    }
}

// ──────────────────────────────────────────────
// Home Screen — запись + список
// ──────────────────────────────────────────────

@Composable
private fun HomeScreen(
    hasPermission: Boolean,
    recordingActive: Boolean,
    recordings: List<Recording>,
    loadError: String?,
    audioLevels: List<Float>,
    onRequestPermission: () -> Unit,
    onToggleRecording: () -> Unit,
    modifier: Modifier = Modifier,
) {
    Box(modifier = modifier.fillMaxSize()) {
        // Particle Field на фоне (только при записи)
        if (recordingActive) {
            ParticleFieldVisualizer(
                audioLevels = audioLevels,
                isRecording = true,
                modifier = Modifier
                    .fillMaxSize()
                    .zIndex(0f)
            )
        }

        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(horizontal = 16.dp)
                .verticalScroll(rememberScrollState())
                .zIndex(1f),
            horizontalAlignment = Alignment.CenterHorizontally
        ) {
            Spacer(modifier = Modifier.height(8.dp))
            WelcomeBlock()
            Spacer(modifier = Modifier.height(20.dp))

            if (!hasPermission) {
                Text(
                    text = "Для записи нужен доступ к микрофону",
                    style = MaterialTheme.typography.bodyLarge,
                    modifier = Modifier.padding(vertical = 8.dp)
                )
                FilledTonalButton(onClick = onRequestPermission) {
                    Text("Разрешить")
                }
            } else {
                // Статус записи
                Text(
                    text = if (recordingActive) "Слушаю..." else "Запись остановлена",
                    style = MaterialTheme.typography.titleMedium,
                    color = if (recordingActive)
                        MaterialTheme.colorScheme.secondary
                    else
                        MaterialTheme.colorScheme.onSurfaceVariant,
                )
                Spacer(modifier = Modifier.height(12.dp))
                FilledTonalButton(onClick = onToggleRecording) {
                    Text(if (recordingActive) "Остановить" else "Начать запись")
                }
            }

            Spacer(modifier = Modifier.height(24.dp))
            Text(
                text = "Записи",
                style = MaterialTheme.typography.titleMedium,
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(bottom = 8.dp)
            )

            loadError?.let { err ->
                Text(
                    text = "Ошибка: $err",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.error,
                    modifier = Modifier.padding(8.dp)
                )
            }

            RecordingListScreen(
                recordings = recordings,
                modifier = Modifier.weight(1f)
            )
        }
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
        Column(modifier = Modifier.padding(16.dp)) {
            Text(
                text = greeting,
                style = MaterialTheme.typography.titleLarge,
                color = MaterialTheme.colorScheme.onPrimaryContainer,
            )
            Spacer(modifier = Modifier.height(8.dp))
            Text(
                text = "Reflexio слушает речь и извлекает смысл. Только важное.",
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onPrimaryContainer,
            )
        }
    }
}
