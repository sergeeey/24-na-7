package com.reflexio.app.domain.services

import android.Manifest
import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Intent
import android.content.pm.PackageManager
import android.media.AudioFormat
import android.media.AudioRecord
import android.media.MediaRecorder
import android.os.Build
import android.os.IBinder
import android.os.PowerManager
import android.util.Log
import androidx.core.app.NotificationCompat
import androidx.core.content.ContextCompat
import com.reflexio.app.BuildConfig
import com.reflexio.app.R
import com.reflexio.app.data.db.PendingUploadDao
import com.reflexio.app.data.db.RecordingDao
import com.reflexio.app.data.db.RecordingDatabase
import com.reflexio.app.data.model.PendingUpload
import com.reflexio.app.data.model.PendingUploadStatus
import com.reflexio.app.data.model.Recording
import com.reflexio.app.data.model.RecordingStatus
import com.reflexio.app.data.model.TransportStatus
import com.reflexio.app.data.model.UploadRetryPolicy
import com.reflexio.app.debug.DebugLog
import com.reflexio.app.domain.network.EnrichmentApiClient
import com.reflexio.app.domain.network.IngestWebSocketClient
import com.reflexio.app.domain.pipeline.PipelineDiagnostics
import com.reflexio.app.domain.vad.VadSegmentWriter
import com.reflexio.app.domain.workers.UploadWorker
import com.reflexio.app.ui.MainActivity
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.io.File
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import java.util.UUID

/**
 * Фоновый сервис записи аудио 24/7 с VAD.
 * Записывает только сегменты с речью в WAV, сохраняет в filesDir/audio_records и Room.
 */
class AudioRecordingService : Service() {

    private var audioRecord: AudioRecord? = null
    private var isRecording = false
    private val scope = CoroutineScope(Dispatchers.Default + Job())
    private var recordingDao: RecordingDao? = null
    private var pendingUploadDao: PendingUploadDao? = null
    // ПОЧЕМУ WakeLock: без него CPU засыпает при выключенном экране,
    // AudioRecord.read() перестаёт получать данные. PARTIAL_WAKE_LOCK держит CPU,
    // но позволяет экрану выключиться — минимальный расход батареи.
    private var wakeLock: PowerManager.WakeLock? = null
    // ПОЧЕМУ один wsClient на весь сервис: persistent WebSocket — один TCP+TLS handshake
    // вместо нового на каждый 3-секундный сегмент. Sequential sending через Mutex внутри.
    private var wsClient: IngestWebSocketClient? = null

    companion object {
        private const val SAMPLE_RATE = 16000
        private const val CHANNEL_CONFIG = AudioFormat.CHANNEL_IN_MONO
        private const val AUDIO_FORMAT = AudioFormat.ENCODING_PCM_16BIT
        private const val TAG = "AudioRecordingService"
        private const val CHANNEL_ID = "reflexio_recording"
        private const val NOTIFICATION_ID = 1001

        /** Эмулятор: 10.0.2.2 -> хост. Реальное устройство: BuildConfig.SERVER_WS_URL_DEVICE (IP ПК). */
        private fun isEmulator(): Boolean =
            Build.FINGERPRINT.contains("generic") || Build.MODEL.contains("sdk") || Build.MODEL.contains("Android SDK")
    }

    override fun onCreate() {
        DebugLog.log("C", "AudioRecordingService.kt:onCreate:entry", "Service onCreate", mapOf("thread" to Thread.currentThread().name))
        super.onCreate()
        createNotificationChannel()
        try {
            DebugLog.log("C", "AudioRecordingService.kt:onCreate:before_getInstance", "calling getInstance", emptyMap())
            val db = RecordingDatabase.getInstance(this)
            recordingDao = db.recordingDao()
            pendingUploadDao = db.pendingUploadDao()
            DebugLog.log("C", "AudioRecordingService.kt:onCreate:dao_ok", "recordingDao assigned", emptyMap())
        } catch (e: Exception) {
            DebugLog.log("C", "AudioRecordingService.kt:onCreate:catch", "Database init failed", mapOf("message" to (e.message ?: ""), "type" to (e.javaClass.simpleName)))
            Log.e(TAG, "Database init failed", e)
            stopSelf()
            return
        }
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        DebugLog.log("C", "AudioRecordingService.kt:onStartCommand", "onStartCommand", mapOf("daoNull" to (recordingDao == null)))
        Log.d(TAG, "Service started")
        if (recordingDao == null) return START_STICKY
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED) {
            Log.w(TAG, "RECORD_AUDIO not granted, stopping service")
            stopSelf()
            return START_STICKY
        }
        startForeground(NOTIFICATION_ID, createForegroundNotification())
        acquireWakeLock()
        val baseUrl = if (isEmulator()) BuildConfig.SERVER_WS_URL else BuildConfig.SERVER_WS_URL_DEVICE
        wsClient = IngestWebSocketClient(baseUrl = baseUrl, apiKey = BuildConfig.SERVER_API_KEY)
        startRecording()
        // UploadWorker — fallback для offline: подберёт pending записи при появлении сети
        UploadWorker.enqueue(this)
        return START_STICKY
    }

    private fun createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(
                CHANNEL_ID,
                getString(R.string.notification_channel_name),
                NotificationManager.IMPORTANCE_LOW
            ).apply { setShowBadge(false) }
            val manager = getSystemService(NotificationManager::class.java)
            manager.createNotificationChannel(channel)
        }
    }

    private fun createForegroundNotification(): Notification {
        val pendingIntent = PendingIntent.getActivity(
            this,
            0,
            Intent(this, MainActivity::class.java),
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )
        return NotificationCompat.Builder(this, CHANNEL_ID)
            .setContentTitle(getString(R.string.app_name))
            .setContentText("Reflexio: запись и очередь синхронизации активны")
            .setSmallIcon(android.R.drawable.ic_btn_speak_now)
            .setContentIntent(pendingIntent)
            .setOngoing(true)
            .build()
    }

    private fun startRecording() {
        if (isRecording) return

        scope.launch {
            try {
                val minBufferSize = AudioRecord.getMinBufferSize(SAMPLE_RATE, CHANNEL_CONFIG, AUDIO_FORMAT)
                if (minBufferSize == AudioRecord.ERROR || minBufferSize == AudioRecord.ERROR_BAD_VALUE || minBufferSize <= 0) {
                    Log.e(TAG, "AudioRecord.getMinBufferSize failed or unsupported: $minBufferSize")
                    stopSelf()
                    return@launch
                }
                val bufferSize = minBufferSize * 2

                audioRecord = AudioRecord(
                    MediaRecorder.AudioSource.MIC,
                    SAMPLE_RATE,
                    CHANNEL_CONFIG,
                    AUDIO_FORMAT,
                    bufferSize
                )

                if (audioRecord?.state != AudioRecord.STATE_INITIALIZED) {
                    Log.e(TAG, "AudioRecord failed to initialize")
                    audioRecord?.release()
                    audioRecord = null
                    stopSelf()
                    return@launch
                }

                val record = audioRecord!!
                record.startRecording()
                isRecording = true

                recordAudioWithVad(record)
            } catch (e: Exception) {
                Log.e(TAG, "Error starting recording", e)
                stopSelf()
            }
        }
    }

    private suspend fun recordAudioWithVad(record: AudioRecord) {
        val audioDir = File(filesDir, "audio_records").apply { mkdirs() }
        val baseTimestamp = SimpleDateFormat("yyyyMMdd_HHmmss", Locale.US).format(Date())
        var segmentIndex = 0
        val frameSize = VadSegmentWriter.FRAME_SIZE
        val frameBuffer = ShortArray(frameSize)
        var pendingOffset = 0

        VadSegmentWriter().use { vadWriter ->
            while (isRecording) {
                val toRead = frameSize - pendingOffset
                val read = record.read(frameBuffer, pendingOffset, toRead)
                if (read < 0) break
                if (read > 0) pendingOffset += read
                if (pendingOffset >= frameSize) {
                    vadWriter.processFrame(frameBuffer)?.let { segments ->
                        for (segmentSamples in segments) {
                            segmentIndex++
                            val file = File(audioDir, "segment_${baseTimestamp}_${segmentIndex.toString().padStart(3, '0')}.wav")
                            writeSegmentToWav(segmentSamples, file)
                            insertSegmentRecording(file, segmentSamples.size)
                        }
                    }
                    pendingOffset = 0
                }
                delay(5)
            }
            vadWriter.flush()?.let { segmentSamples ->
                segmentIndex++
                val file = File(audioDir, "segment_${baseTimestamp}_${segmentIndex.toString().padStart(3, '0')}.wav")
                writeSegmentToWav(segmentSamples, file)
                insertSegmentRecording(file, segmentSamples.size)
            }
        }
    }

    private fun writeSegmentToWav(samples: ShortArray, file: File) {
        val dataSize = samples.size * 2
        val header = ByteArray(44)
        writeWavHeader(header, dataSize, SAMPLE_RATE)
        file.outputStream().use { fos ->
            fos.write(header)
            fos.write(samples.toByteArray())
        }
    }

    private suspend fun insertSegmentRecording(file: File, sampleCount: Int) {
        val durationSeconds = sampleCount / SAMPLE_RATE
        val recording = Recording(
            segmentId = UUID.randomUUID().toString(),
            filePath = file.absolutePath,
            durationSeconds = durationSeconds.toLong(),
            createdAt = System.currentTimeMillis(),
            transcription = null,
            status = RecordingStatus.PENDING_UPLOAD
        )
        try {
            val id = withContext(Dispatchers.IO) { recordingDao!!.insert(recording) }
            withContext(Dispatchers.IO) {
                pendingUploadDao?.upsert(
                    PendingUpload(
                        recordingId = id,
                        segmentId = recording.segmentId,
                        filePath = file.absolutePath,
                    )
                )
                PipelineDiagnostics.setStage(this@AudioRecordingService, "queued")
            }
            // ПОЧЕМУ sendAudioToServer напрямую (не scope.launch):
            // IngestWebSocketClient внутри использует Mutex — sequential отправка.
            // scope.launch создавал 10+ параллельных WebSocket → timeout → потеря данных.
            // UploadWorker подберёт pending записи если онлайн-отправка не прошла.
            sendAudioToServer(file, id)
        } catch (e: Exception) {
            Log.e(TAG, "Failed to insert recording", e)
        }
    }

    private fun writeWavHeader(header: ByteArray, dataSize: Int, sampleRate: Int) {
        val totalSize = dataSize + 36
        header[0] = 'R'.code.toByte()
        header[1] = 'I'.code.toByte()
        header[2] = 'F'.code.toByte()
        header[3] = 'F'.code.toByte()
        writeInt(header, 4, totalSize)
        header[8] = 'W'.code.toByte()
        header[9] = 'A'.code.toByte()
        header[10] = 'V'.code.toByte()
        header[11] = 'E'.code.toByte()
        header[12] = 'f'.code.toByte()
        header[13] = 'm'.code.toByte()
        header[14] = 't'.code.toByte()
        header[15] = ' '.code.toByte()
        writeInt(header, 16, 16)
        writeShort(header, 20, 1)
        writeShort(header, 22, 1)
        writeInt(header, 24, sampleRate)
        writeInt(header, 28, sampleRate * 2)
        writeShort(header, 32, 2)
        writeShort(header, 34, 16)
        header[36] = 'd'.code.toByte()
        header[37] = 'a'.code.toByte()
        header[38] = 't'.code.toByte()
        header[39] = 'a'.code.toByte()
        writeInt(header, 40, dataSize)
    }

    private fun writeInt(arr: ByteArray, offset: Int, value: Int) {
        arr[offset] = (value and 0xFF).toByte()
        arr[offset + 1] = ((value shr 8) and 0xFF).toByte()
        arr[offset + 2] = ((value shr 16) and 0xFF).toByte()
        arr[offset + 3] = ((value shr 24) and 0xFF).toByte()
    }

    private fun writeShort(arr: ByteArray, offset: Int, value: Int) {
        arr[offset] = (value and 0xFF).toByte()
        arr[offset + 1] = ((value shr 8) and 0xFF).toByte()
    }

    private fun ShortArray.toByteArray(): ByteArray {
        return ByteArray(size * 2) { i ->
            val s = this[i / 2]
            if (i % 2 == 0) (s.toInt() and 0xFF).toByte() else ((s.toInt() shr 8) and 0xFF).toByte()
        }
    }

    private suspend fun sendAudioToServer(file: File, recordingId: Long) {
        val client = wsClient ?: return
        PipelineDiagnostics.setStage(this, "uploaded")
        val currentRecording = withContext(Dispatchers.IO) { recordingDao?.getById(recordingId) }
        val result = client.sendSegment(
            file = file,
            segmentId = currentRecording?.segmentId,
            capturedAt = currentRecording?.createdAt,
        ) { stage ->
            PipelineDiagnostics.setStage(this@AudioRecordingService, stage)
        }
        withContext(Dispatchers.IO) {
            val dao = recordingDao ?: return@withContext
            val rec = dao.getById(recordingId) ?: return@withContext
            if (result.isSuccess) {
                val ingestResult = result.getOrNull()
                dao.update(
                    rec.copy(
                        transcription = ingestResult?.transcription,
                        serverFileId = ingestResult?.fileId,
                        status = RecordingStatus.PROCESSED
                    )
                )
                pendingUploadDao?.deleteByRecordingId(recordingId)
                PipelineDiagnostics.setStage(this@AudioRecordingService, "server_acked")
                PipelineDiagnostics.setStage(this@AudioRecordingService, "transcribed")
                PipelineDiagnostics.clearError(this@AudioRecordingService)
                runCatching { if (file.exists()) file.delete() }
                PipelineDiagnostics.setStage(this@AudioRecordingService, "deleted")
                ingestResult?.fileId?.let { fileId ->
                    scope.launch { fetchEnrichment(recordingId, fileId) }
                }
            } else {
                PipelineDiagnostics.setStage(this@AudioRecordingService, "error")
                PipelineDiagnostics.setError(this@AudioRecordingService, result.exceptionOrNull()?.message)
                val pending = pendingUploadDao?.findByRecordingId(recordingId)
                val next = if (pending == null) {
                    PendingUpload(
                        recordingId = recordingId,
                        segmentId = rec.segmentId,
                        filePath = file.absolutePath,
                        retryCount = 1,
                        nextAttemptAt = UploadRetryPolicy.nextAttemptAt(
                            System.currentTimeMillis(),
                            1,
                        ),
                        lastError = result.exceptionOrNull()?.message,
                        lastErrorCode = "transport_error",
                        transportStatus = TransportStatus.RETRY_WAIT,
                        status = PendingUploadStatus.PENDING
                    )
                } else {
                    pending.copy(
                        retryCount = pending.retryCount + 1,
                        nextAttemptAt = UploadRetryPolicy.nextAttemptAt(
                            System.currentTimeMillis(),
                            pending.retryCount + 1,
                        ),
                        lastError = result.exceptionOrNull()?.message,
                        lastErrorCode = "transport_error",
                        transportStatus = if (pending.retryCount + 1 >= UploadRetryPolicy.MAX_RETRY_ATTEMPTS) {
                            TransportStatus.QUARANTINED
                        } else {
                            TransportStatus.RETRY_WAIT
                        },
                        status = if (pending.retryCount + 1 >= UploadRetryPolicy.MAX_RETRY_ATTEMPTS) {
                            PendingUploadStatus.FAILED
                        } else {
                            PendingUploadStatus.PENDING
                        }
                    )
                }
                pendingUploadDao?.upsert(next)
                if (next.status == PendingUploadStatus.FAILED) {
                    dao.update(rec.copy(status = RecordingStatus.FAILED))
                } else {
                    dao.update(rec.copy(status = RecordingStatus.PENDING_UPLOAD))
                }
                UploadWorker.enqueue(this@AudioRecordingService)
            }
        }
    }

    private suspend fun fetchEnrichment(recordingId: Long, fileId: String) {
        delay(3000L)
        val baseUrl = if (isEmulator()) BuildConfig.SERVER_WS_URL else BuildConfig.SERVER_WS_URL_DEVICE
        val httpUrl = baseUrl.replace("ws://", "http://").replace("wss://", "https://")
        val apiClient = EnrichmentApiClient(baseUrl = httpUrl, apiKey = BuildConfig.SERVER_API_KEY)

        repeat(3) { attempt ->
            val enrichment = apiClient.fetchEnrichment(fileId)
            if (enrichment != null) {
                withContext(Dispatchers.IO) {
                    val dao = recordingDao ?: return@withContext
                    val rec = dao.getById(recordingId) ?: return@withContext
                    dao.update(
                        rec.copy(
                            summary = enrichment.summary,
                            emotions = enrichment.emotions.joinToString(","),
                            topics = enrichment.topics.joinToString(","),
                            tasks = enrichment.tasks,
                            urgency = enrichment.urgency,
                            sentiment = enrichment.sentiment,
                        )
                    )
                }
                return
            }
            if (attempt < 2) delay(5000L)
        }
    }

    private fun acquireWakeLock() {
        val pm = getSystemService(POWER_SERVICE) as PowerManager
        wakeLock = pm.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "reflexio:recording").apply {
            acquire()
        }
        Log.d(TAG, "WakeLock acquired")
    }

    override fun onDestroy() {
        super.onDestroy()
        isRecording = false
        audioRecord?.stop()
        audioRecord?.release()
        audioRecord = null
        // ПОЧЕМУ disconnect здесь: без этого WebSocket висит после остановки сервиса,
        // OkHttp thread pool не завершается, утекает TCP соединение.
        wsClient?.disconnect()
        wsClient = null
        wakeLock?.let { if (it.isHeld) it.release() }
        wakeLock = null
        scope.coroutineContext[Job]?.cancel()
    }

    override fun onBind(intent: Intent?): IBinder? = null
}
