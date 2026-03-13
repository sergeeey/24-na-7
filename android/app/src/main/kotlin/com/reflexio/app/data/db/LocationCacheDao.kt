package com.reflexio.app.data.db

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query
import com.reflexio.app.data.model.CachedLocation

@Dao
interface LocationCacheDao {

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun insertAll(locations: List<CachedLocation>)

    @Query(
        """
        SELECT * FROM location_cache
        WHERE timestampMs BETWEEN :startMs AND :endMs
        ORDER BY timestampMs ASC
        """
    )
    suspend fun locationsForRange(startMs: Long, endMs: Long): List<CachedLocation>

    @Query(
        """
        SELECT resolvedPlace, COUNT(*) as cnt
        FROM location_cache
        WHERE resolvedPlace IS NOT NULL
          AND timestampMs BETWEEN :startMs AND :endMs
        GROUP BY resolvedPlace
        ORDER BY cnt DESC
        """
    )
    suspend fun placeFrequency(startMs: Long, endMs: Long): List<PlaceCount>

    @Query("SELECT MAX(syncedAt) FROM location_cache")
    suspend fun lastSyncTime(): Long?

    @Query("DELETE FROM location_cache WHERE timestampMs < :beforeMs")
    suspend fun deleteOlderThan(beforeMs: Long)
}

data class PlaceCount(
    val resolvedPlace: String,
    val cnt: Int,
)
