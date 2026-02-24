package com.reflexio.app.domain.audio

import android.media.AudioFormat
import android.media.AudioRecord
import android.media.MediaRecorder
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlin.math.*

/**
 * Анализатор аудио-спектра в реальном времени
 * Использует FFT для извлечения частотных полос
 */
class AudioSpectrumAnalyzer(
    private val sampleRate: Int = 16000,
    private val fftSize: Int = 1024
) {
    private var audioRecord: AudioRecord? = null
    private var analysisJob: Job? = null

    // 8 частотных полос (bass, low-mid, mid, high-mid, treble)
    private val _frequencyBands = MutableStateFlow(List(8) { 0f })
    val frequencyBands: StateFlow<List<Float>> = _frequencyBands

    // Границы частотных полос (Гц)
    private val bandRanges = listOf(
        20f to 60f,      // Sub-bass
        60f to 250f,     // Bass
        250f to 500f,    // Low mids
        500f to 2000f,   // Mids
        2000f to 4000f,  // High mids
        4000f to 8000f,  // Presence
        8000f to 12000f, // Brilliance
        12000f to 16000f // Air
    )

    fun start() {
        if (audioRecord != null) return

        val minBufferSize = AudioRecord.getMinBufferSize(
            sampleRate,
            AudioFormat.CHANNEL_IN_MONO,
            AudioFormat.ENCODING_PCM_16BIT
        )

        audioRecord = AudioRecord(
            MediaRecorder.AudioSource.MIC,
            sampleRate,
            AudioFormat.CHANNEL_IN_MONO,
            AudioFormat.ENCODING_PCM_16BIT,
            maxOf(minBufferSize, fftSize * 2)
        )

        audioRecord?.startRecording()

        analysisJob = CoroutineScope(Dispatchers.Default).launch {
            val buffer = ShortArray(fftSize)
            val fft = FFT(fftSize)

            while (isActive) {
                val read = audioRecord?.read(buffer, 0, buffer.size) ?: 0
                if (read > 0) {
                    // Преобразование в float и нормализация
                    val samples = FloatArray(fftSize) { i ->
                        if (i < read) buffer[i] / 32768f else 0f
                    }

                    // Применяем оконную функцию Хэмминга
                    applyHammingWindow(samples)

                    // FFT
                    val spectrum = fft.forward(samples)

                    // Извлекаем уровни для каждой полосы
                    val bands = extractBands(spectrum)

                    _frequencyBands.value = bands
                }

                delay(16) // ~60 FPS
            }
        }
    }

    fun stop() {
        analysisJob?.cancel()
        analysisJob = null
        audioRecord?.stop()
        audioRecord?.release()
        audioRecord = null
    }

    private fun applyHammingWindow(samples: FloatArray) {
        for (i in samples.indices) {
            samples[i] *= (0.54 - 0.46 * cos(2 * PI * i / (samples.size - 1))).toFloat()
        }
    }

    private fun extractBands(spectrum: FloatArray): List<Float> {
        val nyquist = sampleRate / 2f
        val binWidth = nyquist / (spectrum.size / 2)

        return bandRanges.map { (freqMin, freqMax) ->
            val binMin = (freqMin / binWidth).toInt().coerceIn(0, spectrum.size / 2 - 1)
            val binMax = (freqMax / binWidth).toInt().coerceIn(binMin, spectrum.size / 2 - 1)

            // Среднее значение в полосе
            val sum = (binMin..binMax).sumOf { spectrum[it].toDouble() }.toFloat()
            val avg = sum / (binMax - binMin + 1)

            // Нормализация с логарифмическим масштабом
            val normalized = (20 * log10((avg + 1e-6).toDouble())).toFloat()
            val scaled = ((normalized + 60) / 60).coerceIn(0f, 1f)

            // Сглаживание
            scaled.pow(0.5f)
        }
    }
}

/**
 * Быстрое преобразование Фурье (FFT)
 * Простая реализация Radix-2 FFT
 */
private class FFT(private val n: Int) {
    init {
        require(n.countOneBits() == 1) { "FFT size must be power of 2" }
    }

    fun forward(samples: FloatArray): FloatArray {
        require(samples.size == n) { "Samples size must match FFT size" }

        val real = samples.copyOf()
        val imag = FloatArray(n) { 0f }

        // Bit-reversal permutation
        var j = 0
        for (i in 0 until n - 1) {
            if (i < j) {
                val tempR = real[i]
                real[i] = real[j]
                real[j] = tempR

                val tempI = imag[i]
                imag[i] = imag[j]
                imag[j] = tempI
            }

            var m = n / 2
            while (m >= 1 && j >= m) {
                j -= m
                m /= 2
            }
            j += m
        }

        // FFT computation
        var len = 2
        while (len <= n) {
            val angle = -2 * PI / len
            val wlenReal = cos(angle).toFloat()
            val wlenImag = sin(angle).toFloat()

            var i = 0
            while (i < n) {
                var wReal = 1f
                var wImag = 0f

                for (k in 0 until len / 2) {
                    val u = i + k
                    val v = u + len / 2

                    val tReal = real[v] * wReal - imag[v] * wImag
                    val tImag = real[v] * wImag + imag[v] * wReal

                    real[v] = real[u] - tReal
                    imag[v] = imag[u] - tImag
                    real[u] = real[u] + tReal
                    imag[u] = imag[u] + tImag

                    val nextWReal = wReal * wlenReal - wImag * wlenImag
                    val nextWImag = wReal * wlenImag + wImag * wlenReal
                    wReal = nextWReal
                    wImag = nextWImag
                }

                i += len
            }

            len *= 2
        }

        // Magnitude spectrum
        return FloatArray(n) { i ->
            sqrt(real[i] * real[i] + imag[i] * imag[i])
        }
    }
}
