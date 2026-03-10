package com.reflexio.app.data.model

import androidx.room.Entity
import androidx.room.Index
import androidx.room.PrimaryKey

@Entity(
    tableName = "pending_uploads",
    indices = [
        Index(value = ["recordingId"], unique = true),
        Index(value = ["createdAt"]),
        Index(value = ["status"])
    ]
)
data class PendingUpload(
    @PrimaryKey(autoGenerate = true)
    val id: Long = 0,
    val recordingId: Long,
    val segmentId: String? = null,
    val filePath: String,
    val createdAt: Long = System.currentTimeMillis(),
    val retryCount: Int = 0,
    val nextAttemptAt: Long? = null,
    val lastError: String? = null,
    val lastErrorCode: String? = null,
    val transportStatus: String = TransportStatus.QUEUED_LOCAL,
    val status: String = "pending"
)

object PendingUploadStatus {
    const val PENDING = "pending"
    const val FAILED = "failed"
}

object TransportStatus {
    const val QUEUED_LOCAL = "queued_local"
    const val UPLOADING = "uploading"
    const val SERVER_ACKED = "server_acked"
    const val RETRY_WAIT = "retry_wait"
    const val QUARANTINED = "quarantined"
}

object UploadRetryPolicy {
    const val MAX_RETRY_ATTEMPTS = 12

    fun nextAttemptAt(nowMs: Long, retryCount: Int): Long {
        val step = when {
            retryCount <= 1 -> 60_000L
            retryCount == 2 -> 5 * 60_000L
            retryCount == 3 -> 15 * 60_000L
            retryCount <= 5 -> 60 * 60_000L
            else -> 6 * 60 * 60_000L
        }
        return nowMs + step
    }
}
