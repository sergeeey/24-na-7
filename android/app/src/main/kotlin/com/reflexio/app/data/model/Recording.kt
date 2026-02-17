package com.reflexio.app.data.model

import androidx.room.Entity
import androidx.room.Index
import androidx.room.PrimaryKey

object RecordingStatus {
    const val PENDING_UPLOAD = "pending_upload"
    const val UPLOADED = "uploaded"
    const val PROCESSED = "processed"
    const val FAILED = "failed"
}

@Entity(
    tableName = "recordings",
    indices = [
        Index(value = ["createdAt"]),
        Index(value = ["status"])
    ]
)
data class Recording(
    @PrimaryKey(autoGenerate = true)
    val id: Long = 0,
    val filePath: String,
    val durationSeconds: Long,
    val createdAt: Long,
    val transcription: String? = null,
    val status: String = RecordingStatus.PENDING_UPLOAD
)
