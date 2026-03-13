package com.reflexio.app.data.db

import android.content.Context
import androidx.room.Database
import androidx.room.Room
import androidx.room.RoomDatabase
import androidx.room.migration.Migration
import androidx.sqlite.db.SupportSQLiteDatabase
import com.reflexio.app.data.model.CachedCall
import com.reflexio.app.data.model.CachedCalendarEvent
import com.reflexio.app.data.model.CachedHealthMetric
import com.reflexio.app.data.model.CachedLocation
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

val MIGRATION_3_4 = object : Migration(3, 4) {
    override fun migrate(db: SupportSQLiteDatabase) {
        db.execSQL("ALTER TABLE recordings ADD COLUMN segmentId TEXT")
        db.execSQL("ALTER TABLE pending_uploads ADD COLUMN segmentId TEXT")
        db.execSQL("ALTER TABLE pending_uploads ADD COLUMN nextAttemptAt INTEGER")
        db.execSQL("ALTER TABLE pending_uploads ADD COLUMN lastErrorCode TEXT")
        db.execSQL("ALTER TABLE pending_uploads ADD COLUMN transportStatus TEXT NOT NULL DEFAULT 'queued_local'")
    }
}

// ПОЧЕМУ отдельная таблица а не JOIN с recordings:
// call_log_cache = локальный кэш ContentResolver, независим от серверных данных.
// Matching звонков с записями — domain-level логика, не DB-level.
val MIGRATION_4_5 = object : Migration(4, 5) {
    override fun migrate(db: SupportSQLiteDatabase) {
        db.execSQL(
            """
            CREATE TABLE IF NOT EXISTS call_log_cache (
                callTimestampMs INTEGER NOT NULL PRIMARY KEY,
                contactName TEXT NOT NULL,
                durationSeconds INTEGER NOT NULL,
                type TEXT NOT NULL,
                syncedAt INTEGER NOT NULL
            )
            """.trimIndent()
        )
        db.execSQL("CREATE INDEX IF NOT EXISTS index_call_log_cache_contactName ON call_log_cache(contactName)")
    }
}

val MIGRATION_5_6 = object : Migration(5, 6) {
    override fun migrate(db: SupportSQLiteDatabase) {
        db.execSQL(
            """
            CREATE TABLE IF NOT EXISTS calendar_event_cache (
                eventId INTEGER NOT NULL PRIMARY KEY,
                title TEXT NOT NULL,
                startMs INTEGER NOT NULL,
                endMs INTEGER NOT NULL,
                location TEXT,
                allDay INTEGER NOT NULL,
                syncedAt INTEGER NOT NULL
            )
            """.trimIndent()
        )
        db.execSQL("CREATE INDEX IF NOT EXISTS index_calendar_event_cache_startMs ON calendar_event_cache(startMs)")
    }
}

val MIGRATION_6_7 = object : Migration(6, 7) {
    override fun migrate(db: SupportSQLiteDatabase) {
        db.execSQL(
            """
            CREATE TABLE IF NOT EXISTS health_metric_cache (
                id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                metricType TEXT NOT NULL,
                value REAL NOT NULL,
                unit TEXT NOT NULL,
                syncedAt INTEGER NOT NULL
            )
            """.trimIndent()
        )
        db.execSQL("CREATE UNIQUE INDEX IF NOT EXISTS index_health_metric_cache_date_metricType ON health_metric_cache(date, metricType)")
    }
}

val MIGRATION_7_8 = object : Migration(7, 8) {
    override fun migrate(db: SupportSQLiteDatabase) {
        db.execSQL(
            """
            CREATE TABLE IF NOT EXISTS location_cache (
                id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
                latitude REAL NOT NULL,
                longitude REAL NOT NULL,
                accuracy REAL NOT NULL,
                timestampMs INTEGER NOT NULL,
                resolvedPlace TEXT,
                syncedAt INTEGER NOT NULL
            )
            """.trimIndent()
        )
    }
}

@Database(
    entities = [
        Recording::class,
        PendingUpload::class,
        CachedCall::class,
        CachedCalendarEvent::class,
        CachedHealthMetric::class,
        CachedLocation::class,
    ],
    version = 8,
    exportSchema = false
)
abstract class RecordingDatabase : RoomDatabase() {

    abstract fun recordingDao(): RecordingDao
    abstract fun pendingUploadDao(): PendingUploadDao
    abstract fun callLogCacheDao(): CallLogCacheDao
    abstract fun calendarCacheDao(): CalendarCacheDao
    abstract fun healthMetricDao(): HealthMetricDao
    abstract fun locationCacheDao(): LocationCacheDao

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
                    .addMigrations(
                        MIGRATION_1_2, MIGRATION_2_3, MIGRATION_3_4, MIGRATION_4_5,
                        MIGRATION_5_6, MIGRATION_6_7, MIGRATION_7_8,
                    )
                    .build()
                    .also { INSTANCE = it }
            }
        }
    }
}
