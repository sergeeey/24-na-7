package com.reflexio.app.data.health

import android.content.Context
import android.util.Log
import androidx.health.connect.client.HealthConnectClient
import androidx.health.connect.client.records.HeartRateRecord
import androidx.health.connect.client.records.SleepSessionRecord
import androidx.health.connect.client.records.StepsRecord
import androidx.health.connect.client.request.ReadRecordsRequest
import androidx.health.connect.client.time.TimeRangeFilter
import com.reflexio.app.data.model.CachedHealthMetric
import java.time.Instant
import java.time.LocalDate
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.time.temporal.ChronoUnit

// ПОЧЕМУ class а не object: Health Connect client требует context и может быть
// недоступен (приложение не установлено). Object не может graceful degrade.
class HealthConnectReader(context: Context) {

    companion object {
        private const val TAG = "HealthConnectReader"

        fun isAvailable(context: Context): Boolean {
            return HealthConnectClient.getSdkStatus(context) == HealthConnectClient.SDK_AVAILABLE
        }
    }

    private val client: HealthConnectClient? = try {
        if (isAvailable(context)) HealthConnectClient.getOrCreate(context) else null
    } catch (e: Exception) {
        Log.w(TAG, "Health Connect unavailable", e)
        null
    }

    suspend fun readSleep(daysBack: Int = 7): List<CachedHealthMetric> {
        val c = client ?: return emptyList()
        val now = Instant.now()
        val start = now.minus(daysBack.toLong(), ChronoUnit.DAYS)
        val syncedAt = System.currentTimeMillis()

        return try {
            val response = c.readRecords(
                ReadRecordsRequest(
                    recordType = SleepSessionRecord::class,
                    timeRangeFilter = TimeRangeFilter.between(start, now),
                )
            )
            response.records.groupBy { record ->
                record.startTime.atZone(ZoneId.systemDefault()).toLocalDate()
            }.map { (date, sessions) ->
                val totalHours = sessions.sumOf { session ->
                    java.time.Duration.between(session.startTime, session.endTime).toMinutes()
                } / 60.0
                CachedHealthMetric(
                    date = date.format(DateTimeFormatter.ISO_LOCAL_DATE),
                    metricType = "sleep_hours",
                    value = totalHours,
                    unit = "hours",
                    syncedAt = syncedAt,
                )
            }
        } catch (e: Exception) {
            Log.w(TAG, "Failed to read sleep", e)
            emptyList()
        }
    }

    suspend fun readSteps(daysBack: Int = 7): List<CachedHealthMetric> {
        val c = client ?: return emptyList()
        val now = Instant.now()
        val start = now.minus(daysBack.toLong(), ChronoUnit.DAYS)
        val syncedAt = System.currentTimeMillis()

        return try {
            val response = c.readRecords(
                ReadRecordsRequest(
                    recordType = StepsRecord::class,
                    timeRangeFilter = TimeRangeFilter.between(start, now),
                )
            )
            response.records.groupBy { record ->
                record.startTime.atZone(ZoneId.systemDefault()).toLocalDate()
            }.map { (date, records) ->
                CachedHealthMetric(
                    date = date.format(DateTimeFormatter.ISO_LOCAL_DATE),
                    metricType = "steps",
                    value = records.sumOf { it.count }.toDouble(),
                    unit = "count",
                    syncedAt = syncedAt,
                )
            }
        } catch (e: Exception) {
            Log.w(TAG, "Failed to read steps", e)
            emptyList()
        }
    }

    suspend fun readHeartRate(daysBack: Int = 7): List<CachedHealthMetric> {
        val c = client ?: return emptyList()
        val now = Instant.now()
        val start = now.minus(daysBack.toLong(), ChronoUnit.DAYS)
        val syncedAt = System.currentTimeMillis()

        return try {
            val response = c.readRecords(
                ReadRecordsRequest(
                    recordType = HeartRateRecord::class,
                    timeRangeFilter = TimeRangeFilter.between(start, now),
                )
            )
            val samplesByDate = mutableMapOf<LocalDate, MutableList<Long>>()
            for (record in response.records) {
                val date = record.startTime.atZone(ZoneId.systemDefault()).toLocalDate()
                val samples = samplesByDate.getOrPut(date) { mutableListOf() }
                record.samples.forEach { samples.add(it.beatsPerMinute) }
            }
            samplesByDate.map { (date, bpmList) ->
                CachedHealthMetric(
                    date = date.format(DateTimeFormatter.ISO_LOCAL_DATE),
                    metricType = "heart_rate_avg",
                    value = bpmList.average(),
                    unit = "bpm",
                    syncedAt = syncedAt,
                )
            }
        } catch (e: Exception) {
            Log.w(TAG, "Failed to read heart rate", e)
            emptyList()
        }
    }
}
