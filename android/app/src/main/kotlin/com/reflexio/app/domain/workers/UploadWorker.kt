package com.reflexio.app.domain.workers

import android.os.Build
import android.util.Log
import androidx.work.Constraints
import androidx.work.CoroutineWorker
import androidx.work.ExistingWorkPolicy
import androidx.work.NetworkType
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.WorkerParameters
import com.reflexio.app.BuildConfig
import com.reflexio.app.data.db.RecordingDatabase
import com.reflexio.app.data.model.PendingUploadStatus
import com.reflexio.app.data.model.RecordingStatus
import com.reflexio.app.data.model.TransportStatus
import com.reflexio.app.data.model.UploadRetryPolicy
import com.reflexio.app.domain.network.IngestWebSocketClient
import com.reflexio.app.domain.pipeline.PipelineDiagnostics
import java.io.File

class UploadWorker(
    appContext: android.content.Context,
    params: WorkerParameters,
) : CoroutineWorker(appContext, params) {

    override suspend fun doWork(): Result {
        val db = RecordingDatabase.getInstance(applicationContext)
        val pendingDao = db.pendingUploadDao()
        val recordingDao = db.recordingDao()

        val baseUrl = if (isEmulator()) BuildConfig.SERVER_WS_URL else BuildConfig.SERVER_WS_URL_DEVICE
        val wsClient = IngestWebSocketClient(baseUrl = baseUrl, apiKey = BuildConfig.SERVER_API_KEY)

        val pending = pendingDao.getRetryable(
            UploadRetryPolicy.MAX_RETRY_ATTEMPTS,
            System.currentTimeMillis(),
        )
        if (pending.isEmpty()) {
            return Result.success()
        }

        var shouldRetry = false
        for (item in pending) {
            val file = File(item.filePath)
            val rec = recordingDao.getById(item.recordingId)
            if (rec == null || !file.exists()) {
                pendingDao.deleteByRecordingId(item.recordingId)
                continue
            }

            PipelineDiagnostics.setStage(applicationContext, "uploaded")
            pendingDao.update(item.copy(transportStatus = TransportStatus.UPLOADING))
            val result = wsClient.sendSegment(
                file = file,
                segmentId = rec.segmentId ?: item.segmentId,
                capturedAt = rec.createdAt,
            ) { stage ->
                PipelineDiagnostics.setStage(applicationContext, stage)
            }
            if (result.isSuccess) {
                val ingest = result.getOrNull()
                recordingDao.update(
                    rec.copy(
                        transcription = ingest?.transcription,
                        serverFileId = ingest?.fileId,
                        status = RecordingStatus.PROCESSED,
                    )
                )
                pendingDao.deleteByRecordingId(item.recordingId)
                PipelineDiagnostics.setStage(applicationContext, "server_acked")
                PipelineDiagnostics.setStage(applicationContext, "transcribed")
                PipelineDiagnostics.clearError(applicationContext)
                runCatching { if (file.exists()) file.delete() }
                PipelineDiagnostics.setStage(applicationContext, "deleted")
            } else {
                val nextRetries = item.retryCount + 1
                val err = result.exceptionOrNull()?.message
                PipelineDiagnostics.setStage(applicationContext, "error")
                PipelineDiagnostics.setError(applicationContext, err)
                if (nextRetries >= UploadRetryPolicy.MAX_RETRY_ATTEMPTS) {
                    recordingDao.update(rec.copy(status = RecordingStatus.FAILED))
                    pendingDao.update(
                        item.copy(
                            retryCount = nextRetries,
                            nextAttemptAt = UploadRetryPolicy.nextAttemptAt(
                                System.currentTimeMillis(),
                                nextRetries,
                            ),
                            lastError = err,
                            lastErrorCode = "transport_error",
                            transportStatus = TransportStatus.QUARANTINED,
                            status = PendingUploadStatus.FAILED,
                        )
                    )
                } else {
                    recordingDao.update(rec.copy(status = RecordingStatus.PENDING_UPLOAD))
                    pendingDao.update(
                        item.copy(
                            retryCount = nextRetries,
                            nextAttemptAt = UploadRetryPolicy.nextAttemptAt(
                                System.currentTimeMillis(),
                                nextRetries,
                            ),
                            lastError = err,
                            lastErrorCode = "transport_error",
                            transportStatus = TransportStatus.RETRY_WAIT,
                            status = PendingUploadStatus.PENDING,
                        )
                    )
                    shouldRetry = true
                }
                Log.w(TAG, "Upload failed recId=${item.recordingId} retry=$nextRetries error=$err")
            }
        }

        return if (shouldRetry) Result.retry() else Result.success()
    }

    companion object {
        private const val TAG = "UploadWorker"
        private const val WORK_NAME = "reflexio_upload_worker"

        fun enqueue(context: android.content.Context) {
            val constraints = Constraints.Builder()
                .setRequiredNetworkType(NetworkType.CONNECTED)
                .build()

            val request = OneTimeWorkRequestBuilder<UploadWorker>()
                .setConstraints(constraints)
                .build()

            WorkManager.getInstance(context).enqueueUniqueWork(
                WORK_NAME,
                ExistingWorkPolicy.KEEP,
                request,
            )
        }

        private fun isEmulator(): Boolean =
            Build.FINGERPRINT.contains("generic") ||
                Build.MODEL.contains("sdk") ||
                Build.MODEL.contains("Android SDK")
    }
}
