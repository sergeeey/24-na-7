package com.reflexio.app.domain.contacts

import com.reflexio.app.data.model.CachedCall
import com.reflexio.app.data.model.Recording

/**
 * Привязывает записи Reflexio к телефонным звонкам по временному окну.
 *
 * ПОЧЕМУ окно = duration + 300сек: после важного звонка человек в течение ~5 мин
 * проговаривает вслух итоги ("Марат сказал что..."). Это самые ценные записи.
 * До звонка — 60сек буфер на подготовку.
 */
object CallRecordingLinker {

    private const val BUFFER_BEFORE_MS = 60_000L   // 1 мин до звонка
    private const val BUFFER_AFTER_MS = 300_000L    // 5 мин после звонка

    data class CallWithRecordings(
        val call: CachedCall,
        val linkedRecordings: List<Recording>,
    )

    /**
     * Для списка звонков одного контакта находит записи Reflexio,
     * попавшие во временное окно каждого звонка.
     */
    fun link(
        calls: List<CachedCall>,
        recordings: List<Recording>,
    ): List<CallWithRecordings> {
        if (calls.isEmpty() || recordings.isEmpty()) return emptyList()

        return calls.map { call ->
            val windowStart = call.callTimestampMs - BUFFER_BEFORE_MS
            val windowEnd = call.callTimestampMs + (call.durationSeconds * 1000L) + BUFFER_AFTER_MS

            val linked = recordings.filter { rec ->
                rec.createdAt in windowStart..windowEnd
            }

            CallWithRecordings(call = call, linkedRecordings = linked)
        }
    }
}
