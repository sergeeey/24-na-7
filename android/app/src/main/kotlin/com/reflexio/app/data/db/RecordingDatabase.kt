package com.reflexio.app.data.db

import android.content.Context
import androidx.room.Database
import androidx.room.Room
import androidx.room.RoomDatabase
import androidx.room.migration.Migration
import androidx.sqlite.db.SupportSQLiteDatabase
import com.reflexio.app.data.model.PendingUpload
import com.reflexio.app.data.model.Recording

// ПОЧЕМУ fallbackToDestructiveMigration НЕ используем:
// У пользователя могут быть записи в БД. Destructive migration удалит их.
// Вместо этого — explicit migration с ALTER TABLE ADD COLUMN для каждого нового поля.
val MIGRATION_1_2 = object : Migration(1, 2) {
    override fun migrate(db: SupportSQLiteDatabase) {
        db.execSQL("ALTER TABLE recordings ADD COLUMN serverFileId TEXT")
        db.execSQL("ALTER TABLE recordings ADD COLUMN summary TEXT")
        db.execSQL("ALTER TABLE recordings ADD COLUMN emotions TEXT")
        db.execSQL("ALTER TABLE recordings ADD COLUMN topics TEXT")
        db.execSQL("ALTER TABLE recordings ADD COLUMN tasks TEXT")
        db.execSQL("ALTER TABLE recordings ADD COLUMN urgency TEXT")
        db.execSQL("ALTER TABLE recordings ADD COLUMN sentiment TEXT")
    }
}

val MIGRATION_2_3 = object : Migration(2, 3) {
    override fun migrate(db: SupportSQLiteDatabase) {
        db.execSQL(
            """
            CREATE TABLE IF NOT EXISTS pending_uploads (
                id INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
                recordingId INTEGER NOT NULL,
                filePath TEXT NOT NULL,
                createdAt INTEGER NOT NULL,
                retryCount INTEGER NOT NULL,
                lastError TEXT,
                status TEXT NOT NULL
            )
            """.trimIndent()
        )
        db.execSQL("CREATE UNIQUE INDEX IF NOT EXISTS index_pending_uploads_recordingId ON pending_uploads(recordingId)")
        db.execSQL("CREATE INDEX IF NOT EXISTS index_pending_uploads_createdAt ON pending_uploads(createdAt)")
        db.execSQL("CREATE INDEX IF NOT EXISTS index_pending_uploads_status ON pending_uploads(status)")
    }
}

@Database(
    entities = [Recording::class, PendingUpload::class],
    version = 3,
    exportSchema = false
)
abstract class RecordingDatabase : RoomDatabase() {

    abstract fun recordingDao(): RecordingDao
    abstract fun pendingUploadDao(): PendingUploadDao

    companion object {
        @Volatile
        private var INSTANCE: RecordingDatabase? = null

        fun getInstance(context: Context): RecordingDatabase {
            return INSTANCE ?: synchronized(this) {
                INSTANCE ?: Room.databaseBuilder(
                    context.applicationContext,
                    RecordingDatabase::class.java,
                    "reflexio_recordings.db"
                )
                    .addMigrations(MIGRATION_1_2, MIGRATION_2_3)
                    .build()
                    .also { INSTANCE = it }
            }
        }
    }
}
