package com.reflexio.app.data.model

import androidx.room.Entity
import androidx.room.Index
import androidx.room.PrimaryKey

// ПОЧЕМУ Room кэш: ContentResolver query на 30 дней звонков = 50-200мс.
// Для PeopleScreen ranking нужен агрегат (GROUP BY contactName), из Room = 1 запрос.
@Entity(
    tableName = "call_log_cache",
    indices = [Index(value = ["contactName"])]
)
data class CachedCall(
    @PrimaryKey val callTimestampMs: Long,
    val contactName: String,
    val durationSeconds: Int,
    val type: String,  // "incoming" | "outgoing" | "missed"
    val syncedAt: Long,
)
