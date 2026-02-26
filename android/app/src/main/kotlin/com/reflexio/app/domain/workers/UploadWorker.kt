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
import com.reflexio.app.data.model.RecordingStatus
import com.reflexio.app.domain.network.IngestWebSocketClient
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

        val pending = pendingDao.getPending()
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

            val result = wsClient.sendSegment(file)
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
                runCatching { if (file.exists()) file.delete() }
            } else {
                val nextRetries = item.retryCount + 1
                val err = result.exceptionOrNull()?.message
                if (nextRetries >= 3) {
                    recordingDao.update(rec.copy(status = RecordingStatus.FAILED))
                    pendingDao.update(item.copy(retryCount = nextRetries, lastError = err, status = "failed"))
                } else {
                    pendingDao.update(item.copy(retryCount = nextRetries, lastError = err, status = "pending"))
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
