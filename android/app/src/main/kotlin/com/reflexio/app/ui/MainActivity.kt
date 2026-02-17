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
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.runtime.State
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.core.content.ContextCompat
import com.reflexio.app.data.db.RecordingDao
import com.reflexio.app.data.db.RecordingDatabase
import com.reflexio.app.data.model.Recording
import com.reflexio.app.debug.DebugLog
import com.reflexio.app.domain.services.AudioRecordingService
import com.reflexio.app.ui.screens.AnalyticsScreen
import com.reflexio.app.ui.screens.DailySummaryScreen
import com.reflexio.app.ui.screens.RecordingListScreen
import com.reflexio.app.BuildConfig

class MainActivity : ComponentActivity() {

    private val hasRecordingPermissionState = mutableStateOf(false)

    private val permissionLauncher = registerForActivityResult(
        ActivityResultContracts.RequestMultiplePermissions()
    ) { _ ->
        hasRecordingPermissionState.value = hasRequiredPermissions()
        if (hasRequiredPermissions()) startRecordingService()
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        // #region agent log
        DebugLog.log("A", "MainActivity.kt:onCreate:entry", "onCreate started", mapOf("thread" to Thread.currentThread().name))
        // #endregion
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        try {
            onCreateImpl(savedInstanceState)
        } catch (e: Throwable) {
            android.util.Log.e("MainActivity", "onCreate failed", e)
            setContent {
                MaterialTheme {
                    Text(
                        text = "Ошибка запуска: ${e.message}\n\n${e.javaClass.simpleName}",
                        modifier = Modifier.padding(16.dp)
                    )
                }
            }
        }
    }

    @Suppress("UNUSED_PARAMETER")
    private fun onCreateImpl(_savedInstanceState: Bundle?) {
        val dao = try {
            // #region agent log
            DebugLog.log("A", "MainActivity.kt:getInstance:before", "calling getInstance", emptyMap())
            // #endregion
            val db = RecordingDatabase.getInstance(applicationContext)
            // #region agent log
            DebugLog.log("A", "MainActivity.kt:getInstance:after", "getInstance ok", emptyMap())
            // #endregion
            db.recordingDao()
        } catch (e: Exception) {
            // #region agent log
            DebugLog.log("A", "MainActivity.kt:getInstance:catch", "Database init failed", mapOf("message" to (e.message ?: ""), "type" to (e.javaClass.simpleName)))
            // #endregion
            android.util.Log.e("MainActivity", "Database init failed", e)
            setContent {
                MaterialTheme {
                    Text(
                        text = "Database error: ${e.message}",
                        modifier = Modifier.padding(16.dp)
                    )
                }
            }
            return
        }
        hasRecordingPermissionState.value = hasRequiredPermissions()
        // #region agent log
        DebugLog.log("B", "MainActivity.kt:setContent:before", "setting RecordingApp with dao", emptyMap())
        // #endregion
        setContent {
            RecordingApp(
                recordingDao = dao,
                hasRecordingPermission = hasRecordingPermissionState,
                onRequestPermission = { permissionLauncher.launch(getRequiredPermissions()) },
                onStartRecording = { startRecordingService() },
                onStopRecording = {
                    val intent = Intent(this, AudioRecordingService::class.java)
                    stopService(intent)
                }
            )
        }
        if (hasRequiredPermissions()) {
            startRecordingService()
        } else {
            permissionLauncher.launch(getRequiredPermissions())
        }
    } // onCreateImpl

    private fun hasRequiredPermissions(): Boolean {
        return getRequiredPermissions().all {
            ContextCompat.checkSelfPermission(this, it) == PackageManager.PERMISSION_GRANTED
        }
    }

    private fun getRequiredPermissions(): Array<String> {
        val list = mutableListOf(Manifest.permission.RECORD_AUDIO)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            list.add(Manifest.permission.POST_NOTIFICATIONS)
        }
        return list.toTypedArray()
    }

    private fun startRecordingService() {
        val serviceIntent = Intent(this, AudioRecordingService::class.java)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            startForegroundService(serviceIntent)
        } else {
            startService(serviceIntent)
        }
    }
}

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
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.primaryContainer),
        shape = MaterialTheme.shapes.medium
    ) {
        Column(modifier = Modifier.padding(12.dp)) {
            Text(
                text = greeting,
                style = MaterialTheme.typography.titleLarge
            )
            Spacer(modifier = Modifier.height(6.dp))
            Text(
                text = "Reflexio тихо слушает речь, извлекает смысл и помогает осмыслять день — без архива, только важное.",
                style = MaterialTheme.typography.bodyMedium
            )
            Spacer(modifier = Modifier.height(8.dp))
            Text(
                text = "• Работает в фоне, без кнопок\n• Итог дня за минуты\n• Только смысл, не архив",
                style = MaterialTheme.typography.bodySmall
            )
        }
    }
}

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
    var showDailySummary by remember { mutableStateOf(false) }
    var showAnalytics by remember { mutableStateOf(false) }
    var recordings by remember { mutableStateOf<List<Recording>>(emptyList()) }
    var loadError by remember { mutableStateOf<String?>(null) }
    val baseHttpUrl = remember {
        val ws = if (BuildConfig.DEBUG) BuildConfig.SERVER_WS_URL else BuildConfig.SERVER_WS_URL_DEVICE
        ws.replace("ws://", "http://").replace("wss://", "https://")
    }
    LaunchedEffect(Unit) {
        // #region agent log
        com.reflexio.app.debug.DebugLog.log("B", "RecordingApp.kt:LaunchedEffect:before_collect", "about to collect getAllRecordings", mapOf("thread" to Thread.currentThread().name))
        // #endregion
        try {
            recordingDao.getAllRecordings().collect { recordings = it }
        } catch (e: Exception) {
            // #region agent log
            com.reflexio.app.debug.DebugLog.log("B", "RecordingApp.kt:LaunchedEffect:collect_catch", "collect failed", mapOf("message" to (e.message ?: ""), "type" to (e.javaClass.simpleName)))
            // #endregion
            android.util.Log.e("RecordingApp", "getAllRecordings failed", e)
            loadError = e.message ?: e.javaClass.simpleName
        }
    }

    MaterialTheme {
        if (showDailySummary) {
            DailySummaryScreen(
                onBack = { showDailySummary = false },
                baseHttpUrl = baseHttpUrl
            )
            return@MaterialTheme
        }
        if (showAnalytics) {
            AnalyticsScreen(
                onBack = { showAnalytics = false },
                onOpenDailySummary = { showAnalytics = false; showDailySummary = true }
            )
            return@MaterialTheme
        }
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(16.dp)
                .verticalScroll(rememberScrollState()),
            horizontalAlignment = Alignment.CenterHorizontally
        ) {
            WelcomeBlock()
            Spacer(modifier = Modifier.height(16.dp))
            Text(
                text = "Reflexio Recording",
                style = MaterialTheme.typography.headlineMedium
            )
            Spacer(modifier = Modifier.height(8.dp))
            if (!hasPermission) {
                Text(
                    text = "Для записи нужен доступ к микрофону",
                    style = MaterialTheme.typography.bodyLarge,
                    modifier = Modifier.padding(vertical = 8.dp)
                )
                Button(onClick = onRequestPermission) {
                    Text("Разрешить")
                }
                Spacer(modifier = Modifier.height(16.dp))
            } else {
                Text(
                    text = if (recordingActive) "Запись идёт в фоне…" else "Запись остановлена",
                    style = MaterialTheme.typography.bodyLarge
                )
                Spacer(modifier = Modifier.height(8.dp))
                Button(
                    onClick = {
                        if (recordingActive) {
                            onStopRecording()
                            recordingActive = false
                        } else {
                            onStartRecording()
                            recordingActive = true
                        }
                    }
                ) {
                    Text(if (recordingActive) "Остановить запись" else "Запустить запись")
                }
                Spacer(modifier = Modifier.height(8.dp))
                Button(onClick = { showDailySummary = true }) {
                    Text("Итог дня")
                }
                Spacer(modifier = Modifier.height(8.dp))
                Button(onClick = { showAnalytics = true }) {
                    Text("Аналитика")
                }
            }
            Spacer(modifier = Modifier.height(16.dp))
            Text(
                text = "Diary",
                style = MaterialTheme.typography.titleMedium
            )
            loadError?.let { err ->
                Text(
                    text = "Ошибка загрузки: $err",
                    style = MaterialTheme.typography.bodySmall,
                    modifier = Modifier.padding(8.dp)
                )
            }
            Spacer(modifier = Modifier.height(8.dp))
            RecordingListScreen(
                recordings = recordings,
                modifier = Modifier.weight(1f)
            )
        }
    }
}
