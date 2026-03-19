package com.reflexio.app.data.db

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query
import androidx.room.Update
import com.reflexio.app.data.model.Recording
import kotlinx.coroutines.flow.Flow

@Dao
interface RecordingDao {

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun insert(recording: Recording): Long

    @Query("SELECT * FROM recordings ORDER BY createdAt DESC")
    fun getAllRecordings(): Flow<List<Recording>>

    @Update
    suspend fun update(recording: Recording)

    @Query("SELECT * FROM recordings WHERE status = :status ORDER BY createdAt ASC")
    fun getRecordingsByStatus(status: String): Flow<List<Recording>>

    @Query("SELECT * FROM recordings WHERE id = :id LIMIT 1")
    suspend fun getById(id: Long): Recording?

    @Query("SELECT COUNT(*) FROM recordings WHERE status = :status")
    suspend fun getCountByStatus(status: String): Int

    @Query("SELECT filePath FROM recordings")
    suspend fun getAllFilePaths(): List<String>

    @Query("SELECT createdAt FROM recordings WHERE status = 'processed' ORDER BY createdAt DESC LIMIT 1")
    suspend fun getLastProcessedCreatedAt(): Long?

    // WHY: CallRecordingLinker needs a List, not Flow. Recent 30 days is enough for linking.
    @Query("SELECT * FROM recordings WHERE createdAt >= :sinceMs ORDER BY createdAt DESC")
    suspend fun getRecordingsSince(sinceMs: Long): List<Recording>
}
