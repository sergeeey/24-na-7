package com.reflexio.app.data.db

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query
import com.reflexio.app.data.model.CachedHealthMetric

@Dao
interface HealthMetricDao {

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun insertAll(metrics: List<CachedHealthMetric>)

    @Query("SELECT * FROM health_metric_cache WHERE date = :date")
    suspend fun metricsForDate(date: String): List<CachedHealthMetric>

    @Query(
        """
        SELECT * FROM health_metric_cache
        WHERE metricType = :type
        ORDER BY date DESC
        LIMIT :limit
        """
    )
    suspend fun recentByType(type: String, limit: Int = 7): List<CachedHealthMetric>

    @Query(
        """
        SELECT * FROM health_metric_cache
        WHERE date BETWEEN :startDate AND :endDate
        ORDER BY date ASC, metricType ASC
        """
    )
    suspend fun metricsForRange(startDate: String, endDate: String): List<CachedHealthMetric>

    @Query("SELECT MAX(syncedAt) FROM health_metric_cache")
    suspend fun lastSyncTime(): Long?
}
