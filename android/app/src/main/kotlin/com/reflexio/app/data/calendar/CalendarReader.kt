package com.reflexio.app.data.calendar

import android.content.ContentResolver
import android.provider.CalendarContract
import com.reflexio.app.data.model.CachedCalendarEvent

object CalendarReader {

    private const val DAYS_BACK = 30
    private const val MS_PER_DAY = 86_400_000L

    fun readEvents(resolver: ContentResolver): List<CachedCalendarEvent> {
        val events = mutableListOf<CachedCalendarEvent>()
        val cutoff = System.currentTimeMillis() - DAYS_BACK * MS_PER_DAY
        val now = System.currentTimeMillis()

        val projection = arrayOf(
            CalendarContract.Events._ID,
            CalendarContract.Events.TITLE,
            CalendarContract.Events.DTSTART,
            CalendarContract.Events.DTEND,
            CalendarContract.Events.EVENT_LOCATION,
            CalendarContract.Events.ALL_DAY,
        )

        resolver.query(
            CalendarContract.Events.CONTENT_URI,
            projection,
            "${CalendarContract.Events.DTSTART} > ?",
            arrayOf(cutoff.toString()),
            "${CalendarContract.Events.DTSTART} DESC",
        )?.use { cursor ->
            val idIdx = cursor.getColumnIndexOrThrow(CalendarContract.Events._ID)
            val titleIdx = cursor.getColumnIndexOrThrow(CalendarContract.Events.TITLE)
            val startIdx = cursor.getColumnIndexOrThrow(CalendarContract.Events.DTSTART)
            val endIdx = cursor.getColumnIndexOrThrow(CalendarContract.Events.DTEND)
            val locIdx = cursor.getColumnIndexOrThrow(CalendarContract.Events.EVENT_LOCATION)
            val allDayIdx = cursor.getColumnIndexOrThrow(CalendarContract.Events.ALL_DAY)

            while (cursor.moveToNext()) {
                val title = cursor.getString(titleIdx)
                if (title.isNullOrBlank()) continue
                val startMs = cursor.getLong(startIdx)
                // ПОЧЕМУ fallback endMs = startMs + 1 час: некоторые события не имеют DTEND
                val endMs = if (cursor.isNull(endIdx)) startMs + 3_600_000L else cursor.getLong(endIdx)

                events.add(
                    CachedCalendarEvent(
                        eventId = cursor.getLong(idIdx),
                        title = title,
                        startMs = startMs,
                        endMs = endMs,
                        location = cursor.getString(locIdx)?.takeIf { it.isNotBlank() },
                        allDay = cursor.getInt(allDayIdx) == 1,
                        syncedAt = now,
                    )
                )
            }
        }
        return events
    }
}
