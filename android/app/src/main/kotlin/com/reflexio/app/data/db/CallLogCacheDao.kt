package com.reflexio.app.data.db

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query
import com.reflexio.app.data.model.CachedCall

@Dao
interface CallLogCacheDao {

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun insertAll(calls: List<CachedCall>)

    @Query("DELETE FROM call_log_cache WHERE syncedAt < :olderThanMs")
    suspend fun deleteOlderThan(olderThanMs: Long)

    @Query(
        """
        SELECT contactName,
               COUNT(*) AS callCount,
               SUM(durationSeconds) AS totalSeconds,
               MAX(callTimestampMs) AS lastCallMs
        FROM call_log_cache
        WHERE contactName != ''
        GROUP BY contactName
        ORDER BY callCount DESC
        """
    )
    suspend fun aggregateByContact(): List<CallAggregate>

    @Query(
        """
        SELECT * FROM call_log_cache
        WHERE contactName = :name
        ORDER BY callTimestampMs DESC
        LIMIT :limit
        """
    )
    suspend fun callsForContact(name: String, limit: Int = 20): List<CachedCall>

    @Query("SELECT MAX(syncedAt) FROM call_log_cache")
    suspend fun lastSyncTime(): Long?
}

data class CallAggregate(
    val contactName: String,
    val callCount: Int,
    val totalSeconds: Int,
    val lastCallMs: Long,
)
