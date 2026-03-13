package com.reflexio.app.data.db

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query
import androidx.room.Update
import com.reflexio.app.data.model.PendingUpload

@Dao
interface PendingUploadDao {
    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun upsert(item: PendingUpload): Long

    @Update
    suspend fun update(item: PendingUpload)

    @Query("SELECT * FROM pending_uploads WHERE status = 'pending' ORDER BY createdAt ASC")
    suspend fun getPending(): List<PendingUpload>

    @Query(
        "SELECT * FROM pending_uploads " +
            "WHERE ((status = 'pending') OR (status = 'failed' AND retryCount < :maxRetryCount)) " +
            "AND (nextAttemptAt IS NULL OR nextAttemptAt <= :nowMs) " +
            "ORDER BY createdAt ASC"
    )
    suspend fun getRetryable(maxRetryCount: Int, nowMs: Long): List<PendingUpload>

    @Query("SELECT COUNT(*) FROM pending_uploads WHERE status = 'pending'")
    suspend fun getPendingCount(): Int

    @Query("SELECT * FROM pending_uploads WHERE recordingId = :recordingId LIMIT 1")
    suspend fun findByRecordingId(recordingId: Long): PendingUpload?

    @Query("DELETE FROM pending_uploads WHERE recordingId = :recordingId")
    suspend fun deleteByRecordingId(recordingId: Long)

    @Query("SELECT filePath FROM pending_uploads")
    suspend fun getAllFilePaths(): List<String>

    @Query("SELECT * FROM pending_uploads WHERE status = 'failed' ORDER BY createdAt DESC LIMIT 1")
    suspend fun getLastFailed(): PendingUpload?
}
