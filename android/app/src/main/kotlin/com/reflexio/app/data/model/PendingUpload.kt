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
    val filePath: String,
    val createdAt: Long = System.currentTimeMillis(),
    val retryCount: Int = 0,
    val lastError: String? = null,
    val status: String = "pending"
)
