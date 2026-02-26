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

    @Query("SELECT * FROM pending_uploads WHERE recordingId = :recordingId LIMIT 1")
    suspend fun findByRecordingId(recordingId: Long): PendingUpload?

    @Query("DELETE FROM pending_uploads WHERE recordingId = :recordingId")
    suspend fun deleteByRecordingId(recordingId: Long)
}
