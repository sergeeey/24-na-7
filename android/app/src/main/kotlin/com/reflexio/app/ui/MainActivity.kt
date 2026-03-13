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
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.DateRange
import androidx.compose.material.icons.filled.Home
import androidx.compose.material.icons.filled.Insights
import androidx.compose.material.icons.filled.RecordVoiceOver
import androidx.compose.material.icons.filled.Search
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.runtime.Composable
import androidx.compose.runtime.State
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.produceState
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.unit.dp
import androidx.core.content.ContextCompat
import com.reflexio.app.data.db.RecordingDatabase
import com.reflexio.app.domain.network.ServerEndpointResolver
import com.reflexio.app.domain.services.AudioRecordingService
import com.reflexio.app.ui.components.AmbientBackdrop
import com.reflexio.app.ui.components.BalanceWheelVisualizer
import com.reflexio.app.ui.screens.AskScreen
import com.reflexio.app.ui.screens.DailySummaryScreen
import com.reflexio.app.ui.screens.MirrorScreen
import com.reflexio.app.ui.screens.PeopleScreen
import com.reflexio.app.ui.screens.PersonScreen
import com.reflexio.app.ui.screens.SplashScreen
import com.reflexio.app.ui.screens.ThreadsScreen
import com.reflexio.app.ui.screens.VoiceEnrollmentScreen
import com.reflexio.app.ui.theme.ReflexioTheme
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

// ПОЧЕМУ enum а не sealed class: фиксированный набор экранов, sealed class — overkill
private enum class Screen(val title: String, val icon: ImageVector) {
    ASK("Спросить", Icons.Default.Search),
    DAY("Итог", Icons.Default.DateRange),
    PEOPLE("Люди", Icons.Default.Home),
    MIRROR("Зеркало", Icons.Default.Insights),
    RECORD("Запись", Icons.Default.RecordVoiceOver),
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
    var selectedTab by remember { mutableIntStateOf(Screen.ASK.ordinal) }
    var showVoiceEnrollment by remember { mutableStateOf(false) }
    var showThreads by remember { mutableStateOf(false) }
    var personDraft by rememberSaveable { mutableStateOf("") }
    var askDraft by rememberSaveable { mutableStateOf("") }

    // ПОЧЕМУ isEmulator() а не BuildConfig.DEBUG: DEBUG=true и на телефоне и на эмуляторе.
    // 10.0.2.2 работает ТОЛЬКО в эмуляторе. На телефоне с adb reverse нужен localhost.
    val baseHttpUrl by produceState(initialValue = ServerEndpointResolver.primaryHttpUrl()) {
        value = withContext(Dispatchers.IO) {
            ServerEndpointResolver.resolveUiHttpBaseUrl()
        }
    }

    val screens = Screen.entries

    Box(modifier = Modifier.fillMaxSize()) {
        AmbientBackdrop()

        Scaffold(
            topBar = {
                TopAppBar(
                    title = {
                        Text(
                            text = screens[selectedTab].title,
                            style = MaterialTheme.typography.titleLarge
                        )
                    },
                    actions = {
                        IconButton(onClick = { showVoiceEnrollment = true }) {
                            Icon(
                                imageVector = Icons.Default.RecordVoiceOver,
                                contentDescription = "Голос",
                            )
                        }
                    },
                    colors = TopAppBarDefaults.topAppBarColors(
                        containerColor = Color.Transparent,
                        titleContentColor = MaterialTheme.colorScheme.onBackground,
                    ),
                )
            },
            bottomBar = {
                NavigationBar(
                    containerColor = MaterialTheme.colorScheme.surface.copy(alpha = 0.88f),
                    tonalElevation = 0.dp,
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
            containerColor = Color.Transparent,
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
                    0 -> AskScreen(
                        baseHttpUrl = baseHttpUrl,
                        initialQuestion = askDraft,
                        onInitialQuestionConsumed = { askDraft = "" },
                        onOpenSearch = { query ->
                            askDraft = query
                        },
                        onOpenPeople = { selectedTab = Screen.PEOPLE.ordinal },
                        modifier = Modifier.padding(padding),
                    )
                    1 -> DailySummaryScreen(
                        baseHttpUrl = baseHttpUrl,
                        modifier = Modifier.padding(padding),
                    )
                    2 -> PeopleScreen(
                        baseHttpUrl = baseHttpUrl,
                        onOpenPerson = { name -> personDraft = name },
                        modifier = Modifier.padding(padding),
                    )
                    3 -> MirrorScreen(
                        baseHttpUrl = baseHttpUrl,
                        onOpenPerson = { name -> personDraft = name },
                        onOpenThreads = { showThreads = true },
                        modifier = Modifier.padding(padding),
                    )
                    4 -> RecordScreen(
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
                }
            }
        }

        androidx.compose.animation.AnimatedVisibility(
            visible = showVoiceEnrollment,
            enter = androidx.compose.animation.slideInVertically { it },
            exit = androidx.compose.animation.slideOutVertically { it },
        ) {
            Box(
                modifier = Modifier
                    .fillMaxSize()
                    .background(MaterialTheme.colorScheme.background),
            ) {
                Column {
                    Row(
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(horizontal = 16.dp, vertical = 8.dp),
                        horizontalArrangement = Arrangement.SpaceBetween,
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        Text("Голос", style = MaterialTheme.typography.titleLarge)
                        TextButton(onClick = { showVoiceEnrollment = false }) {
                            Text("Закрыть")
                        }
                    }
                    VoiceEnrollmentScreen(
                        baseHttpUrl = baseHttpUrl,
                        modifier = Modifier.weight(1f),
                    )
                }
            }
        }

        androidx.compose.animation.AnimatedVisibility(
            visible = showThreads,
            enter = androidx.compose.animation.slideInVertically { it },
            exit = androidx.compose.animation.slideOutVertically { it },
        ) {
            Box(
                modifier = Modifier
                    .fillMaxSize()
                    .background(MaterialTheme.colorScheme.background),
            ) {
                Column {
                    Row(
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(horizontal = 16.dp, vertical = 8.dp),
                        horizontalArrangement = Arrangement.SpaceBetween,
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        Text("Потоки", style = MaterialTheme.typography.titleLarge)
                        TextButton(onClick = { showThreads = false }) {
                            Text("Закрыть")
                        }
                    }
                    ThreadsScreen(
                        baseHttpUrl = baseHttpUrl,
                        modifier = Modifier.weight(1f),
                    )
                }
            }
        }

        androidx.compose.animation.AnimatedVisibility(
            visible = personDraft.isNotBlank(),
            enter = androidx.compose.animation.slideInVertically { it },
            exit = androidx.compose.animation.slideOutVertically { it },
        ) {
            Box(
                modifier = Modifier
                    .fillMaxSize()
                    .background(MaterialTheme.colorScheme.background),
            ) {
                Column {
                    Row(
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(horizontal = 16.dp, vertical = 8.dp),
                        horizontalArrangement = Arrangement.SpaceBetween,
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        Text(personDraft, style = MaterialTheme.typography.titleLarge)
                        TextButton(onClick = { personDraft = "" }) {
                            Text("Закрыть")
                        }
                    }
                    PersonScreen(
                        baseHttpUrl = baseHttpUrl,
                        name = personDraft,
                        onAskPerson = { question ->
                            askDraft = question
                            personDraft = ""
                            selectedTab = Screen.ASK.ordinal
                        },
                        onOpenThreads = {
                            showThreads = true
                        },
                        modifier = Modifier.weight(1f),
                    )
                }
            }
        }
    }
}

@Composable
private fun RecordScreen(
    hasPermission: Boolean,
    recordingActive: Boolean,
    baseHttpUrl: String,
    onRequestPermission: () -> Unit,
    onToggleRecording: () -> Unit,
    modifier: Modifier = Modifier,
) {
    Box(
        modifier = modifier.fillMaxSize(),
    ) {
        BalanceWheelVisualizer(
            baseHttpUrl = baseHttpUrl,
            isRecording = recordingActive,
            hasPermission = hasPermission,
            onToggleRecording = onToggleRecording,
            onRequestPermission = onRequestPermission,
            modifier = Modifier
                .fillMaxWidth()
                .fillMaxHeight(0.965f)
                .align(Alignment.Center)
                .padding(horizontal = 2.dp, vertical = 2.dp),
        )
    }
}
