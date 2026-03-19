package com.reflexio.app.domain.vad

import java.io.Closeable
import kotlin.math.abs
import kotlin.math.max

private const val SAMPLE_RATE = 16000
private const val VAD_FRAME_SIZE = 320
// WHY 75 (1.5s): Evidence-based from multiple sources:
// - Google/Azure ASR: 1000ms for conversation mode
// - Russian psycholinguistics: 700-1500ms inter-sentence pauses
// - Whisper optimal input: 5-15 sec segments (needs context)
// - Always-on + office noise: higher threshold avoids TV false triggers
// 1.5s balances context for Whisper vs not merging unrelated speech.
private const val SILENCE_FRAMES_TO_END = 75 // 1500ms / 20ms
// WHY 1.0 not 0.5: segments < 1s are almost always noise or fragments
// that Whisper hallucinates text for. Raising to 1s reduces garbage.
private const val MIN_SEGMENT_SAMPLES = SAMPLE_RATE * 1 // 1.0 sec
// WHY 25 not 30: gives margin before Whisper medium hallucination zone (>20s).
private const val MAX_SEGMENT_SAMPLES = SAMPLE_RATE * 25 // 25 sec hard cap
private const val INITIAL_SEGMENT_CAPACITY = SAMPLE_RATE * 2 // 2 sec
private const val SOFT_RESET_CAPACITY = SAMPLE_RATE * 8 // 8 sec

private const val NOISE_FLOOR_ALPHA = 0.985f
private const val MIN_NOISE_RMS = 220f
private const val SPEECH_RMS_MULTIPLIER = 2.25f
private const val SPEECH_RMS_ABSOLUTE = 900f
private const val MIN_ZERO_CROSSINGS = 3
private const val MAX_ZERO_CROSSINGS = 140

/**
 * Локальный VAD без native `.so`.
 * Использует комбинацию RMS + zero-crossing heuristics и адаптивный noise floor.
 * Контракт совпадает с прежним writer: завершает сегмент после 300ms тишины.
 */
class VadSegmentWriter : Closeable {

    private var segmentBuffer = ShortArray(INITIAL_SEGMENT_CAPACITY)
    private var segmentSize = 0
    private var inSpeech = false
    private var silenceFrameCount = 0
    private var noiseFloorRms = MIN_NOISE_RMS

    /**
     * Обрабатывает один кадр (320 сэмплов). Возвращает завершённый сегмент
     * или null. Сегмент возвращается после 15 кадров тишины подряд.
     */
    fun processFrame(samples: ShortArray): List<ShortArray>? {
        require(samples.size == VAD_FRAME_SIZE) {
            "Expected frame size $VAD_FRAME_SIZE, got ${samples.size}"
        }
        val completedSegments = mutableListOf<ShortArray>()
        val isSpeech = detectSpeech(samples)
        if (isSpeech) {
            inSpeech = true
            silenceFrameCount = 0
            if (segmentSize + samples.size > MAX_SEGMENT_SAMPLES) {
                finalizeSegment()?.let(completedSegments::add)
                inSpeech = true
            }
            appendSamples(samples)
            return completedSegments.takeIf { it.isNotEmpty() }
        }
        if (inSpeech) {
            if (segmentSize + samples.size > MAX_SEGMENT_SAMPLES) {
                finalizeSegment()?.let(completedSegments::add)
                return completedSegments.takeIf { it.isNotEmpty() }
            }
            appendSamples(samples)
            silenceFrameCount++
            if (silenceFrameCount >= SILENCE_FRAMES_TO_END) {
                finalizeSegment()?.let(completedSegments::add)
            }
            return completedSegments.takeIf { it.isNotEmpty() }
        }
        return null
    }

    /**
     * При остановке записи отдаёт последний накопленный сегмент (если не короче минимума).
     */
    fun flush(): ShortArray? {
        return finalizeSegment()
    }

    override fun close() = Unit

    companion object {
        const val FRAME_SIZE = VAD_FRAME_SIZE
    }

    private fun appendSamples(samples: ShortArray) {
        val requiredSize = segmentSize + samples.size
        ensureCapacity(requiredSize)
        samples.copyInto(
            destination = segmentBuffer,
            destinationOffset = segmentSize,
            startIndex = 0,
            endIndex = samples.size,
        )
        segmentSize = requiredSize
    }

    private fun ensureCapacity(requiredSize: Int) {
        if (requiredSize <= segmentBuffer.size) {
            return
        }
        var newCapacity = segmentBuffer.size.coerceAtLeast(INITIAL_SEGMENT_CAPACITY)
        while (newCapacity < requiredSize) {
            newCapacity = (newCapacity * 2).coerceAtMost(MAX_SEGMENT_SAMPLES)
            if (newCapacity >= requiredSize) {
                break
            }
            if (newCapacity == MAX_SEGMENT_SAMPLES) {
                newCapacity = requiredSize
                break
            }
        }
        segmentBuffer = segmentBuffer.copyOf(newCapacity.coerceAtMost(MAX_SEGMENT_SAMPLES))
    }

    private fun finalizeSegment(): ShortArray? {
        val segment = if (segmentSize >= MIN_SEGMENT_SAMPLES) {
            segmentBuffer.copyOf(segmentSize)
        } else {
            null
        }
        resetSegment()
        return segment
    }

    private fun resetSegment() {
        segmentSize = 0
        inSpeech = false
        silenceFrameCount = 0
        if (segmentBuffer.size > SOFT_RESET_CAPACITY) {
            segmentBuffer = ShortArray(INITIAL_SEGMENT_CAPACITY)
        }
    }

    private fun detectSpeech(samples: ShortArray): Boolean {
        val rms = calculateRms(samples)
        val zeroCrossings = countZeroCrossings(samples)
        val speechThreshold = max(SPEECH_RMS_ABSOLUTE, noiseFloorRms * SPEECH_RMS_MULTIPLIER)
        val isSpeech = rms >= speechThreshold &&
            zeroCrossings in MIN_ZERO_CROSSINGS..MAX_ZERO_CROSSINGS

        if (!isSpeech || !inSpeech) {
            noiseFloorRms = max(
                MIN_NOISE_RMS,
                noiseFloorRms * NOISE_FLOOR_ALPHA + rms * (1f - NOISE_FLOOR_ALPHA),
            )
        }
        return isSpeech
    }

    private fun calculateRms(samples: ShortArray): Float {
        var sum = 0.0
        for (sample in samples) {
            val normalized = sample / 32768.0
            sum += normalized * normalized
        }
        val meanSquare = sum / samples.size.toDouble()
        return (kotlin.math.sqrt(meanSquare) * 32768.0).toFloat()
    }

    private fun countZeroCrossings(samples: ShortArray): Int {
        var crossings = 0
        var prev = samples.first()
        for (i in 1 until samples.size) {
            val curr = samples[i]
            if ((prev < 0 && curr >= 0) || (prev >= 0 && curr < 0)) {
                crossings++
            } else if (abs(curr - prev) > 12000 && (prev == 0.toShort() || curr == 0.toShort())) {
                crossings++
            }
            prev = curr
        }
        return crossings
    }
}
