package com.reflexio.app.domain.vad

import com.konovalov.vad.webrtc.VadWebRTC
import com.konovalov.vad.webrtc.config.FrameSize
import com.konovalov.vad.webrtc.config.Mode
import com.konovalov.vad.webrtc.config.SampleRate
import com.reflexio.app.BuildConfig
import java.io.Closeable

private const val SAMPLE_RATE = 16000
private const val VAD_FRAME_SIZE = 320
private const val SILENCE_FRAMES_TO_END = 15 // 300ms / 20ms
private const val MIN_SEGMENT_SAMPLES = (SAMPLE_RATE * 0.5).toInt() // 0.5 sec

/**
 * Оборачивает WebRTC VAD и буферизует PCM-кадры в сегменты речи.
 * При 300 ms тишины после речи отдаёт завершённый сегмент.
 * Сегменты короче 0.5 с отбрасываются.
 * В debug: режим NORMAL (чувствительнее), в release: VERY_AGGRESSIVE.
 */
class VadSegmentWriter : Closeable {

    private val vad = VadWebRTC(
        sampleRate = SampleRate.SAMPLE_RATE_16K,
        frameSize = FrameSize.FRAME_SIZE_320,
        mode = if (BuildConfig.DEBUG) Mode.NORMAL else Mode.VERY_AGGRESSIVE,
        speechDurationMs = 50,
        silenceDurationMs = 300
    )
    private val segmentBuffer = mutableListOf<Short>()
    private var inSpeech = false
    private var silenceFrameCount = 0

    /**
     * Обрабатывает один кадр (320 сэмплов). Возвращает завершённый сегмент
     * или null. Сегмент возвращается после 15 кадров тишины подряд.
     */
    fun processFrame(samples: ShortArray): List<ShortArray>? {
        require(samples.size == VAD_FRAME_SIZE) {
            "Expected frame size $VAD_FRAME_SIZE, got ${samples.size}"
        }
        val isSpeech = vad.isSpeech(samples)
        if (isSpeech) {
            inSpeech = true
            silenceFrameCount = 0
            segmentBuffer.addAll(samples.toList())
            return null
        }
        if (inSpeech) {
            segmentBuffer.addAll(samples.toList())
            silenceFrameCount++
            if (silenceFrameCount >= SILENCE_FRAMES_TO_END) {
                val segment = segmentBuffer.toShortArray()
                segmentBuffer.clear()
                inSpeech = false
                silenceFrameCount = 0
                return if (segment.size >= MIN_SEGMENT_SAMPLES) listOf(segment) else null
            }
            return null
        }
        return null
    }

    /**
     * При остановке записи отдаёт последний накопленный сегмент (если не короче минимума).
     */
    fun flush(): ShortArray? {
        val segment = if (segmentBuffer.size >= MIN_SEGMENT_SAMPLES) {
            segmentBuffer.toShortArray()
        } else {
            null
        }
        segmentBuffer.clear()
        return segment
    }

    override fun close() {
        (vad as? Closeable)?.close()
    }

    companion object {
        const val FRAME_SIZE = VAD_FRAME_SIZE
    }
}
