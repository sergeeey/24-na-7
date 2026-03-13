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
import com.reflexio.app.domain.network.EnrichmentApiClient
import com.reflexio.app.domain.network.IngestWebSocketClient
import com.reflexio.app.domain.network.ServerEndpointResolver
import com.reflexio.app.domain.pipeline.PipelineDiagnostics
import kotlinx.coroutines.delay
import java.io.File

class UploadWorker(
    appContext: android.content.Context,
    params: WorkerParameters,
) : CoroutineWorker(appContext, params) {

    override suspend fun doWork(): Result {
        val db = RecordingDatabase.getInstance(applicationContext)
        val pendingDao = db.pendingUploadDao()
        val recordingDao = db.recordingDao()

        val baseUrl = ServerEndpointResolver.resolveBackgroundWsUrl()
        Log.d(TAG, "Starting upload worker with baseUrl=$baseUrl")
        val wsClient = IngestWebSocketClient(
            baseUrl = baseUrl,
            apiKey = ServerEndpointResolver.apiKeyForUrl(ServerEndpointResolver.wsToHttp(baseUrl)),
        )

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
                val nextStatus = if (ingest?.fileId != null) {
                    RecordingStatus.UPLOADED
                } else {
                    RecordingStatus.PROCESSED
                }
                recordingDao.update(
                    rec.copy(
                        transcription = ingest?.transcription,
                        serverFileId = ingest?.fileId,
                        status = nextStatus,
                    )
                )
                pendingDao.deleteByRecordingId(item.recordingId)
                PipelineDiagnostics.setStage(applicationContext, "server_acked")
                if (!ingest?.transcription.isNullOrBlank()) {
                    PipelineDiagnostics.setStage(applicationContext, "transcribed")
                }
                PipelineDiagnostics.clearError(applicationContext)
                runCatching { if (file.exists()) file.delete() }
                PipelineDiagnostics.setStage(applicationContext, "deleted")
                ingest?.fileId?.let { fileId ->
                    fetchEnrichment(recordingDao, item.recordingId, fileId)
                }
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
                ExistingWorkPolicy.APPEND_OR_REPLACE,
                request,
            )
        }

        private fun isEmulator(): Boolean =
            Build.FINGERPRINT.contains("generic") ||
                Build.MODEL.contains("sdk") ||
                Build.MODEL.contains("Android SDK")
    }

    private suspend fun fetchEnrichment(
        recordingDao: com.reflexio.app.data.db.RecordingDao,
        recordingId: Long,
        fileId: String,
    ) {
        delay(3000L)
        val httpUrl = ServerEndpointResolver.resolveBackgroundHttpUrl()
        val apiClient = EnrichmentApiClient(
            baseUrl = httpUrl,
            apiKey = ServerEndpointResolver.apiKeyForUrl(httpUrl),
        )
        PipelineDiagnostics.setStage(applicationContext, "enriching")

        repeat(12) { attempt ->
            val enrichment = apiClient.fetchEnrichment(fileId)
            if (enrichment != null) {
                val rec = recordingDao.getById(recordingId) ?: return
                recordingDao.update(
                    rec.copy(
                        summary = enrichment.summary,
                        emotions = enrichment.emotions.joinToString(","),
                        topics = enrichment.topics.joinToString(","),
                        tasks = enrichment.tasks,
                        urgency = enrichment.urgency,
                        sentiment = enrichment.sentiment,
                        status = RecordingStatus.PROCESSED,
                    )
                )
                PipelineDiagnostics.setStage(applicationContext, "enriched")
                return
            }
            if (attempt < 11) delay(5000L)
        }
    }
}
