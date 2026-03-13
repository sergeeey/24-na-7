package com.reflexio.app.data.model

import androidx.room.Entity
import androidx.room.Index
import androidx.room.PrimaryKey

// ПОЧЕМУ composite unique index: одна метрика на один день на один тип.
// Upsert через REPLACE — новые данные перезаписывают старые за тот же день.
@Entity(
    tableName = "health_metric_cache",
    indices = [Index(value = ["date", "metricType"], unique = true)]
)
data class CachedHealthMetric(
    @PrimaryKey(autoGenerate = true) val id: Long = 0,
    val date: String,         // "2026-03-13"
    val metricType: String,   // "sleep_hours" | "steps" | "heart_rate_avg"
    val value: Double,
    val unit: String,         // "hours" | "count" | "bpm"
    val syncedAt: Long,
)
