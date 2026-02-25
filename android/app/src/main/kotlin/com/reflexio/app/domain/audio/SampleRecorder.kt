package com.reflexio.app.domain.audio

import android.media.AudioFormat
import android.media.AudioRecord
import android.media.MediaRecorder
import java.io.File
import java.io.FileOutputStream
import java.nio.ByteBuffer
import java.nio.ByteOrder

private const val SAMPLE_RATE = 16000
private const val MAX_SECONDS = 10

/**
 * Простой WAV рекордер для enrollment образцов.
 *
 * ПОЧЕМУ AudioRecord а не MediaRecorder: MediaRecorder не умеет WAV напрямую
 * (AAC, AMR, MP4 — но не RIFF/WAVE). AudioRecord даёт сырой PCM, мы сами
 * пишем WAV-заголовок. Сервер проверяет magic bytes RIFF/WAVE при валидации.
 *
 * ПОЧЕМУ @Volatile: isRecording читается из IO-потока (запись) и пишется
 * из Main-потока (кнопка Stop). @Volatile гарантирует видимость без синхронизации.
 */
class SampleRecorder {

    @Volatile private var isRecording = false

    /**
     * Блокирующий вызов — запускать на Dispatchers.IO.
     * Записывает до MAX_SECONDS секунд PCM 16-bit 16kHz mono, пишет WAV.
     * Завершается по stop() или по истечении максимального времени.
     */
    fun record(outputFile: File) {
        val minBuf = AudioRecord.getMinBufferSize(
            SAMPLE_RATE,
            AudioFormat.CHANNEL_IN_MONO,
            AudioFormat.ENCODING_PCM_16BIT,
        )
        // ПОЧЕМУ minBuf * 4: запас под джиттер, чтобы OS не дропала кадры
        val bufferSize = minBuf * 4

        val audioRecord = AudioRecord(
            MediaRecorder.AudioSource.MIC,
            SAMPLE_RATE,
            AudioFormat.CHANNEL_IN_MONO,
            AudioFormat.ENCODING_PCM_16BIT,
            bufferSize,
        )

        val pcm = mutableListOf<Byte>()
        // 2 байта на сэмпл (16-bit), 16000 сэмплов/сек, MAX_SECONDS сек
        val maxBytes = SAMPLE_RATE * MAX_SECONDS * 2
        val readBuf = ShortArray(bufferSize / 2)

        audioRecord.startRecording()
        isRecording = true

        while (isRecording && pcm.size < maxBytes) {
            val read = audioRecord.read(readBuf, 0, readBuf.size)
            if (read <= 0) break
            val bytes = ByteBuffer.allocate(read * 2).order(ByteOrder.LITTLE_ENDIAN)
            for (i in 0 until read) bytes.putShort(readBuf[i])
            pcm.addAll(bytes.array().toList())
        }

        audioRecord.stop()
        audioRecord.release()

        writeWav(outputFile, pcm.toByteArray())
    }

    /** Вызывается с Main-потока чтобы прервать record(). */
    fun stop() {
        isRecording = false
    }

    /**
     * Пишет стандартный WAV заголовок (44 байта) + PCM данные.
     *
     * ПОЧЕМУ LITTLE_ENDIAN: WAV — формат Intel (LE), независимо от платформы.
     * fileSize в RIFF = полный размер файла - 8 (сами "RIFF" + 4 байта size).
     */
    private fun writeWav(file: File, pcm: ByteArray) {
        val dataSize = pcm.size
        val header = ByteBuffer.allocate(44).order(ByteOrder.LITTLE_ENDIAN).apply {
            put("RIFF".toByteArray())
            putInt(36 + dataSize)          // fileSize - 8
            put("WAVE".toByteArray())
            put("fmt ".toByteArray())
            putInt(16)                     // PCM chunk size
            putShort(1)                    // format = PCM
            putShort(1)                    // channels = mono
            putInt(SAMPLE_RATE)
            putInt(SAMPLE_RATE * 2)        // byteRate = sampleRate * 2 (16-bit mono)
            putShort(2)                    // blockAlign = 2 байта на сэмпл
            putShort(16)                   // bitsPerSample
            put("data".toByteArray())
            putInt(dataSize)
        }
        FileOutputStream(file).use { out ->
            out.write(header.array())
            out.write(pcm)
        }
    }
}
