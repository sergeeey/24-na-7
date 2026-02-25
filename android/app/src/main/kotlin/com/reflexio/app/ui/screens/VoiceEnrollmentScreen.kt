package com.reflexio.app.ui.screens

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.filled.Mic
import androidx.compose.material.icons.filled.Stop
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.FilledTonalButton
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import com.reflexio.app.BuildConfig
import com.reflexio.app.domain.audio.SampleRecorder
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.MultipartBody
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.asRequestBody
import java.io.File
import java.util.concurrent.TimeUnit

// Цвета в стиле приложения
private val ColorSuccess = Color(0xFF00E5CC)   // DarkSecondary
private val ColorRecording = Color(0xFFFF6B6B) // DarkError

/**
 * Состояния экрана enrollment.
 * ПОЧЕМУ sealed class: явные состояния лучше булевых флагов —
 * компилятор проверяет что all branches handled в when().
 */
private sealed class EnrollState {
    object Idle : EnrollState()
    data class Recording(val slot: Int) : EnrollState()
    object Uploading : EnrollState()
    object Success : EnrollState()
    data class Error(val message: String) : EnrollState()
}

/**
 * Экран создания голосового профиля.
 *
 * Flow: запись 3 образцов (по 5-10 сек) → POST /voice/enroll → профиль создан.
 * После успеха: включить SPEAKER_VERIFICATION_ENABLED=true в .env на сервере.
 *
 * ПОЧЕМУ 3 образца: resemblyzer GE2E строит среднее embedding из нескольких
 * записей — это даёт более устойчивый d-vector чем из одной записи.
 */
@Composable
fun VoiceEnrollmentScreen(
    baseHttpUrl: String,
    modifier: Modifier = Modifier,
) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val recorder = remember { SampleRecorder() }

    // 3 слота: null = не записан, File = готов
    val samples = remember { mutableStateListOf<File?>(null, null, null) }
    var enrollState by remember { mutableStateOf<EnrollState>(EnrollState.Idle) }

    val allRecorded = samples.all { it != null }

    Column(
        modifier = modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(16.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {

        Spacer(modifier = Modifier.height(8.dp))

        Text(
            text = "Голосовой профиль",
            style = MaterialTheme.typography.headlineSmall,
            fontWeight = FontWeight.Bold,
        )

        Spacer(modifier = Modifier.height(8.dp))

        Text(
            text = "Запишите 3 образца своего голоса по 5–10 секунд каждый.\n" +
                    "Говорите естественно — расскажите о своём дне или прочитайте любой текст.",
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            textAlign = TextAlign.Center,
        )

        Spacer(modifier = Modifier.height(24.dp))

        // ── 3 карточки записи ──────────────────────────────────────────
        (0..2).forEach { slot ->
            SampleCard(
                slot = slot,
                file = samples[slot],
                isRecording = enrollState is EnrollState.Recording &&
                        (enrollState as EnrollState.Recording).slot == slot,
                // Разрешаем нажать только если Idle или идёт запись этого слота
                enabled = enrollState is EnrollState.Idle ||
                        (enrollState is EnrollState.Recording &&
                                (enrollState as EnrollState.Recording).slot == slot),
                onStartRecord = {
                    val file = File(context.cacheDir, "enroll_$slot.wav")
                    enrollState = EnrollState.Recording(slot)
                    scope.launch(Dispatchers.IO) {
                        // record() блокирует поток до stop() или MAX_SECONDS
                        recorder.record(file)
                        samples[slot] = file
                        withContext(Dispatchers.Main) {
                            enrollState = EnrollState.Idle
                        }
                    }
                },
                onStopRecord = {
                    // Вызываем из Main-потока, record() завершится в IO-потоке
                    recorder.stop()
                },
            )
            Spacer(modifier = Modifier.height(12.dp))
        }

        Spacer(modifier = Modifier.height(8.dp))

        // ── Кнопка/статус отправки ──────────────────────────────────────
        when (val state = enrollState) {

            is EnrollState.Success -> {
                Icon(
                    imageVector = Icons.Default.CheckCircle,
                    contentDescription = null,
                    tint = ColorSuccess,
                    modifier = Modifier.size(56.dp),
                )
                Spacer(modifier = Modifier.height(12.dp))
                Text(
                    text = "Голосовой профиль создан!",
                    style = MaterialTheme.typography.titleMedium,
                    color = ColorSuccess,
                    fontWeight = FontWeight.Bold,
                )
                Spacer(modifier = Modifier.height(4.dp))
                Text(
                    text = "Для активации включите на сервере:\nSPEAKER_VERIFICATION_ENABLED=true",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    textAlign = TextAlign.Center,
                )
                Spacer(modifier = Modifier.height(16.dp))
                OutlinedButton(
                    onClick = {
                        samples.replaceAll { null }
                        enrollState = EnrollState.Idle
                    },
                ) { Text("Перезаписать профиль") }
            }

            is EnrollState.Error -> {
                Text(
                    text = "Ошибка: ${state.message}",
                    color = MaterialTheme.colorScheme.error,
                    style = MaterialTheme.typography.bodyMedium,
                    textAlign = TextAlign.Center,
                )
                Spacer(modifier = Modifier.height(12.dp))
                Button(onClick = { enrollState = EnrollState.Idle }) {
                    Text("Попробовать снова")
                }
            }

            is EnrollState.Uploading -> {
                CircularProgressIndicator(color = ColorSuccess)
                Spacer(modifier = Modifier.height(12.dp))
                Text(
                    text = "Создаю голосовой профиль…",
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }

            else -> {
                Button(
                    onClick = {
                        scope.launch(Dispatchers.IO) {
                            withContext(Dispatchers.Main) {
                                enrollState = EnrollState.Uploading
                            }
                            enrollSamples(
                                baseHttpUrl = baseHttpUrl,
                                files = samples.filterNotNull(),
                                onSuccess = { enrollState = EnrollState.Success },
                                onError = { msg -> enrollState = EnrollState.Error(msg) },
                            )
                        }
                    },
                    enabled = allRecorded && enrollState is EnrollState.Idle,
                    modifier = Modifier.fillMaxWidth(),
                ) {
                    Text("Создать голосовой профиль")
                }

                if (!allRecorded) {
                    Spacer(modifier = Modifier.height(8.dp))
                    Text(
                        text = "Запишите все 3 образца",
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            }
        }

        Spacer(modifier = Modifier.height(16.dp))
    }
}

// ──────────────────────────────────────────────────────────────────────────────
// Карточка одного образца
// ──────────────────────────────────────────────────────────────────────────────

@Composable
private fun SampleCard(
    slot: Int,
    file: File?,
    isRecording: Boolean,
    enabled: Boolean,
    onStartRecord: () -> Unit,
    onStopRecord: () -> Unit,
) {
    val isDone = file != null && !isRecording

    Card(
        shape = RoundedCornerShape(12.dp),
        colors = CardDefaults.cardColors(
            containerColor = when {
                isRecording -> MaterialTheme.colorScheme.errorContainer
                isDone -> MaterialTheme.colorScheme.primaryContainer
                else -> MaterialTheme.colorScheme.surfaceVariant
            },
        ),
        modifier = Modifier.fillMaxWidth(),
    ) {
        Row(
            modifier = Modifier
                .padding(horizontal = 16.dp, vertical = 14.dp)
                .fillMaxWidth(),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.SpaceBetween,
        ) {
            Column(modifier = Modifier.weight(1f)) {
                Text(
                    text = "Образец ${slot + 1}",
                    style = MaterialTheme.typography.titleSmall,
                    fontWeight = FontWeight.SemiBold,
                )
                Spacer(modifier = Modifier.height(2.dp))
                Text(
                    text = when {
                        isRecording -> "Запись… нажмите Стоп когда закончили"
                        isDone -> "Готово ✓"
                        else -> "5–10 сек речи"
                    },
                    style = MaterialTheme.typography.labelSmall,
                    color = if (isRecording) ColorRecording
                    else MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }

            Spacer(modifier = Modifier.width(12.dp))

            FilledTonalButton(
                onClick = if (isRecording) onStopRecord else onStartRecord,
                enabled = enabled,
            ) {
                Icon(
                    imageVector = if (isRecording) Icons.Default.Stop else Icons.Default.Mic,
                    contentDescription = null,
                    modifier = Modifier.size(16.dp),
                )
                Spacer(modifier = Modifier.width(4.dp))
                Text(
                    text = when {
                        isRecording -> "Стоп"
                        isDone -> "Перезапись"
                        else -> "Запись"
                    },
                )
            }
        }
    }
}

// ──────────────────────────────────────────────────────────────────────────────
// HTTP multipart upload — вынесен из @Composable для чистоты
// ──────────────────────────────────────────────────────────────────────────────

/**
 * POST /voice/enroll с тремя WAV файлами.
 * Вызывается на Dispatchers.IO, колбэки вызываются там же —
 * вызывающий код оборачивает в withContext(Main).
 *
 * ПОЧЕМУ OkHttp напрямую: уже в зависимостях через EnrichmentApiClient,
 * добавлять Retrofit ради одного endpoint — overkill.
 */
private fun enrollSamples(
    baseHttpUrl: String,
    files: List<File>,
    onSuccess: () -> Unit,
    onError: (String) -> Unit,
) {
    try {
        val client = OkHttpClient.Builder()
            .connectTimeout(15, TimeUnit.SECONDS)
            .writeTimeout(30, TimeUnit.SECONDS)
            .readTimeout(30, TimeUnit.SECONDS)
            .build()

        val body = MultipartBody.Builder()
            .setType(MultipartBody.FORM)
            .also { builder ->
                files.forEach { file ->
                    builder.addFormDataPart(
                        name = "files",
                        filename = file.name,
                        body = file.asRequestBody("audio/wav".toMediaType()),
                    )
                }
            }
            .build()

        val request = Request.Builder()
            .url("${baseHttpUrl.removeSuffix("/")}/voice/enroll")
            .apply {
                if (BuildConfig.SERVER_API_KEY.isNotEmpty()) {
                    addHeader("Authorization", "Bearer ${BuildConfig.SERVER_API_KEY}")
                }
            }
            .post(body)
            .build()

        val response = client.newCall(request).execute()
        if (response.isSuccessful) {
            onSuccess()
        } else {
            val errorBody = response.body?.string()?.take(200) ?: "HTTP ${response.code}"
            onError(errorBody)
        }
    } catch (e: Exception) {
        onError(e.message ?: "Нет соединения с сервером")
    }
}
