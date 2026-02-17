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
import android.util.Log
import androidx.core.app.NotificationCompat
import androidx.core.content.ContextCompat
import com.reflexio.app.R
import com.reflexio.app.data.db.RecordingDao
import com.reflexio.app.data.db.RecordingDatabase
import com.reflexio.app.data.model.Recording
import com.reflexio.app.data.model.RecordingStatus
import com.reflexio.app.BuildConfig
import com.reflexio.app.domain.network.IngestWebSocketClient
import com.reflexio.app.debug.DebugLog
import com.reflexio.app.domain.vad.VadSegmentWriter
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

/**
 * Фоновый сервис записи аудио 24/7 с VAD.
 * Записывает только сегменты с речью в WAV, сохраняет в filesDir/audio_records и Room.
 */
class AudioRecordingService : Service() {

    private var audioRecord: AudioRecord? = null
    private var isRecording = false
    private val scope = CoroutineScope(Dispatchers.Default + Job())
    private var recordingDao: RecordingDao? = null

    companion object {
        private const val SAMPLE_RATE = 16000
        private const val CHANNEL_CONFIG = AudioFormat.CHANNEL_IN_MONO
        private const val AUDIO_FORMAT = AudioFormat.ENCODING_PCM_16BIT
        private const val TAG = "AudioRecordingService"
        private const val CHANNEL_ID = "reflexio_recording"
        private const val NOTIFICATION_ID = 1001

        /** Эмулятор: 10.0.2.2 → хост. Реальное устройство: BuildConfig.SERVER_WS_URL_DEVICE (IP ПК). */
        private fun isEmulator(): Boolean =
            Build.FINGERPRINT.contains("generic") || Build.MODEL.contains("sdk") || Build.MODEL.contains("Android SDK")
    }

    override fun onCreate() {
        // #region agent log
        DebugLog.log("C", "AudioRecordingService.kt:onCreate:entry", "Service onCreate", mapOf("thread" to Thread.currentThread().name))
        // #endregion
        super.onCreate()
        createNotificationChannel()
        try {
            // #region agent log
            DebugLog.log("C", "AudioRecordingService.kt:onCreate:before_getInstance", "calling getInstance", emptyMap())
            // #endregion
            recordingDao = RecordingDatabase.getInstance(this).recordingDao()
            // #region agent log
            DebugLog.log("C", "AudioRecordingService.kt:onCreate:dao_ok", "recordingDao assigned", emptyMap())
            // #endregion
        } catch (e: Exception) {
            // #region agent log
            DebugLog.log("C", "AudioRecordingService.kt:onCreate:catch", "Database init failed", mapOf("message" to (e.message ?: ""), "type" to (e.javaClass.simpleName)))
            // #endregion
            Log.e(TAG, "Database init failed", e)
            stopSelf()
            return
        }
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        // #region agent log
        DebugLog.log("C", "AudioRecordingService.kt:onStartCommand", "onStartCommand", mapOf("daoNull" to (recordingDao == null)))
        // #endregion
        Log.d(TAG, "Service started")
        if (recordingDao == null) return START_STICKY
        // Android 14+: FGS type "microphone" требует RECORD_AUDIO до вызова startForeground (логи: SecurityException)
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED) {
            Log.w(TAG, "RECORD_AUDIO not granted, stopping service")
            stopSelf()
            return START_STICKY
        }
        startForeground(NOTIFICATION_ID, createForegroundNotification())
        startRecording()
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
            .setContentText("Recording audio in background…")
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
                    Log.e(TAG, "AudioRecord.getMinBufferSize failed or unsupported (microphone absent/busy): $minBufferSize")
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
                    Log.e(TAG, "AudioRecord failed to initialize (microphone absent or busy)")
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
            var frameCount = 0
            var speechFrameCount = 0
            Log.d(TAG, "Starting VAD recording loop")
            while (isRecording) {
                val toRead = frameSize - pendingOffset
                val read = record.read(frameBuffer, pendingOffset, toRead)
                if (read < 0) {
                    Log.e(TAG, "AudioRecord.read returned error: $read")
                    break
                }
                if (read > 0) pendingOffset += read
                if (pendingOffset >= frameSize) {
                    frameCount++
                    vadWriter.processFrame(frameBuffer)?.let { segments ->
                        speechFrameCount++
                        Log.d(TAG, "VAD detected speech segment #$speechFrameCount (frame $frameCount)")
                        for (segmentSamples in segments) {
                            segmentIndex++
                            val file = File(audioDir, "segment_${baseTimestamp}_${segmentIndex.toString().padStart(3, '0')}.wav")
                            writeSegmentToWav(segmentSamples, file)
                            Log.d(TAG, "Writing segment $segmentIndex to ${file.name} (${segmentSamples.size} samples)")
                            insertSegmentRecording(file, segmentSamples.size)
                        }
                    }
                    if (frameCount % 100 == 0) {
                        Log.d(TAG, "Recording: $frameCount frames processed, $speechFrameCount speech frames")
                    }
                    pendingOffset = 0
                }
                delay(5)
            }
            Log.d(TAG, "Recording loop ended. Total frames: $frameCount, speech frames: $speechFrameCount")
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
            filePath = file.absolutePath,
            durationSeconds = durationSeconds.toLong(),
            createdAt = System.currentTimeMillis(),
            transcription = null,
            status = RecordingStatus.PENDING_UPLOAD
        )
        try {
            val id = withContext(Dispatchers.IO) { 
                recordingDao!!.insert(recording) 
            }
            Log.d(TAG, "Segment saved to DB: id=$id, file=${file.name}, duration=${durationSeconds}s")
            scope.launch { sendAudioToServer(file, id) }
        } catch (e: Exception) {
            Log.e(TAG, "Failed to insert recording to DB", e)
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
        val baseUrl = if (isEmulator()) BuildConfig.SERVER_WS_URL else BuildConfig.SERVER_WS_URL_DEVICE
        val wsClient = IngestWebSocketClient(baseUrl = baseUrl)
        val result = wsClient.sendSegment(file)
        withContext(Dispatchers.IO) {
            val dao = recordingDao ?: return@withContext
            val rec = dao.getById(recordingId) ?: return@withContext
            if (result.isSuccess) {
                dao.update(rec.copy(
                    transcription = result.getOrNull(),
                    status = RecordingStatus.PROCESSED
                ))
                Log.d(TAG, "Uploaded and transcribed: $recordingId")
            } else {
                dao.update(rec.copy(status = RecordingStatus.FAILED))
                Log.e(TAG, "Upload failed for $recordingId", result.exceptionOrNull())
            }
        }
    }

    override fun onDestroy() {
        super.onDestroy()
        isRecording = false
        audioRecord?.stop()
        audioRecord?.release()
        audioRecord = null
        scope.coroutineContext[Job]?.cancel()
    }

    override fun onBind(intent: Intent?): IBinder? = null
}
