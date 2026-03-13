package com.reflexio.app.data.model

import androidx.room.Entity
import androidx.room.PrimaryKey

// ПОЧЕМУ autoGenerate PK а не composite: одна точка может быть в одном месте
// в одно время, но мы не можем гарантировать уникальность (lat,lng,timestamp).
@Entity(tableName = "location_cache")
data class CachedLocation(
    @PrimaryKey(autoGenerate = true) val id: Long = 0,
    val latitude: Double,
    val longitude: Double,
    val accuracy: Float,
    val timestampMs: Long,
    val resolvedPlace: String?,  // "Дом", "Офис", null если не кластеризовано
    val syncedAt: Long,
)
