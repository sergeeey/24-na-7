package com.reflexio.app.data.model

import androidx.room.Entity
import androidx.room.Index
import androidx.room.PrimaryKey

@Entity(
    tableName = "calendar_event_cache",
    indices = [Index(value = ["startMs"])]
)
data class CachedCalendarEvent(
    @PrimaryKey val eventId: Long,
    val title: String,
    val startMs: Long,
    val endMs: Long,
    val location: String?,
    val allDay: Boolean,
    val syncedAt: Long,
)
