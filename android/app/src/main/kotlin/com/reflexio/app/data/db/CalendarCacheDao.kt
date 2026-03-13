package com.reflexio.app.data.db

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query
import com.reflexio.app.data.model.CachedCalendarEvent

@Dao
interface CalendarCacheDao {

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun insertAll(events: List<CachedCalendarEvent>)

    @Query("DELETE FROM calendar_event_cache WHERE syncedAt < :olderThanMs")
    suspend fun deleteOlderThan(olderThanMs: Long)

    // ПОЧЕМУ startMs < :endMs AND endMs > :startMs: стандартная формула перекрытия интервалов.
    // Находит все события, пересекающиеся с заданным временным окном.
    @Query(
        """
        SELECT * FROM calendar_event_cache
        WHERE startMs < :endMs AND endMs > :startMs
        ORDER BY startMs ASC
        """
    )
    suspend fun eventsOverlapping(startMs: Long, endMs: Long): List<CachedCalendarEvent>

    @Query(
        """
        SELECT * FROM calendar_event_cache
        WHERE startMs BETWEEN :dayStartMs AND :dayEndMs
        ORDER BY startMs ASC
        """
    )
    suspend fun eventsForDay(dayStartMs: Long, dayEndMs: Long): List<CachedCalendarEvent>

    @Query("SELECT COUNT(*) FROM calendar_event_cache WHERE startMs BETWEEN :startMs AND :endMs")
    suspend fun eventCountForRange(startMs: Long, endMs: Long): Int

    @Query("SELECT MAX(syncedAt) FROM calendar_event_cache")
    suspend fun lastSyncTime(): Long?
}
