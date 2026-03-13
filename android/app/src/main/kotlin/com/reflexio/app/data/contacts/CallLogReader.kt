package com.reflexio.app.data.contacts

import android.content.ContentResolver
import android.provider.CallLog
import com.reflexio.app.data.model.CachedCall

// ПОЧЕМУ 30 дней: глубже — медленно и бессмысленно для ranking.
// Звонок годовой давности не влияет на текущую важность человека.
object CallLogReader {

    private const val DAYS_BACK = 30
    private const val MS_PER_DAY = 86_400_000L

    fun readCallLog(resolver: ContentResolver): List<CachedCall> {
        val calls = mutableListOf<CachedCall>()
        val cutoff = System.currentTimeMillis() - DAYS_BACK * MS_PER_DAY
        val now = System.currentTimeMillis()

        val projection = arrayOf(
            CallLog.Calls.DATE,
            CallLog.Calls.CACHED_NAME,
            CallLog.Calls.DURATION,
            CallLog.Calls.TYPE,
        )

        resolver.query(
            CallLog.Calls.CONTENT_URI,
            projection,
            "${CallLog.Calls.DATE} > ?",
            arrayOf(cutoff.toString()),
            "${CallLog.Calls.DATE} DESC",
        )?.use { cursor ->
            val dateIdx = cursor.getColumnIndexOrThrow(CallLog.Calls.DATE)
            val nameIdx = cursor.getColumnIndexOrThrow(CallLog.Calls.CACHED_NAME)
            val durationIdx = cursor.getColumnIndexOrThrow(CallLog.Calls.DURATION)
            val typeIdx = cursor.getColumnIndexOrThrow(CallLog.Calls.TYPE)

            while (cursor.moveToNext()) {
                val name = cursor.getString(nameIdx)
                if (name.isNullOrBlank()) continue

                val type = when (cursor.getInt(typeIdx)) {
                    CallLog.Calls.INCOMING_TYPE -> "incoming"
                    CallLog.Calls.OUTGOING_TYPE -> "outgoing"
                    CallLog.Calls.MISSED_TYPE -> "missed"
                    else -> "other"
                }

                calls.add(
                    CachedCall(
                        callTimestampMs = cursor.getLong(dateIdx),
                        contactName = name,
                        durationSeconds = cursor.getInt(durationIdx),
                        type = type,
                        syncedAt = now,
                    )
                )
            }
        }
        return calls
    }
}
