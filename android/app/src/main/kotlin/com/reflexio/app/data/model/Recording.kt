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
    val status: String = RecordingStatus.PENDING_UPLOAD,
    // ПОЧЕМУ serverFileId: это file_id из WebSocket ответа сервера.
    // Нужен для запроса enrichment через GET /enrichment/by-ingest/{file_id}
    val serverFileId: String? = null,
    // Enrichment данные от LLM (приходят async через ~3-5 сек после транскрипции)
    val summary: String? = null,
    val emotions: String? = null,   // JSON array: ["радость", "уверенность"]
    val topics: String? = null,     // JSON array: ["работа", "планирование"]
    val tasks: String? = null,      // JSON array: [{"text":"...", "priority":"high"}]
    val urgency: String? = null,    // low | medium | high
    val sentiment: String? = null   // positive | neutral | negative
)
