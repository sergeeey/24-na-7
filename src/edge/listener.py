"""Edge listener: запись речи с VAD и автоотправка на сервер."""
import webrtcvad
import sounddevice as sd
import numpy as np
import wave
import time
import requests
from pathlib import Path
from datetime import datetime
from typing import Optional

from src.utils.config import settings
from src.utils.logging import setup_logging, get_logger
from src.edge.filters import SpeechFilter

# Настройка логирования
setup_logging()
logger = get_logger("edge")

# Инициализация VAD
vad = webrtcvad.Vad(settings.AUDIO_VAD_AGGRESSIVENESS)

# Инициализация фильтра речи (если включён)
speech_filter = SpeechFilter(
    enabled=settings.FILTER_MUSIC,
    method=settings.FILTER_METHOD,
    sample_rate=settings.AUDIO_SAMPLE_RATE,
    speech_band_low=settings.FILTER_SPEECH_BAND_LOW,
    speech_band_high=settings.FILTER_SPEECH_BAND_HIGH,
    energy_threshold=settings.FILTER_ENERGY_THRESHOLD,
    high_freq_threshold=settings.FILTER_HIGH_FREQ_THRESHOLD,
)

# Создаём директорию для локальных записей
settings.RECORDINGS_PATH.mkdir(parents=True, exist_ok=True)


def write_wave(path: Path, audio_frames: list[bytes], sample_rate: int) -> None:
    """Записывает аудио в WAV файл."""
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)  # Моно
        wf.setsampwidth(2)  # 16-bit
        wf.setframerate(sample_rate)
        wf.writeframes(b"".join(audio_frames))


def upload_audio(file_path: Path, api_url: str) -> bool:
    """
    Отправляет аудиофайл на сервер.
    
    Returns:
        True если успешно, False в противном случае
    """
    try:
        with open(file_path, "rb") as f:
            files = {"file": (file_path.name, f, "audio/wav")}
            response = requests.post(
                f"{api_url}/ingest/audio",
                files=files,
                timeout=30,
            )
            response.raise_for_status()
            result = response.json()
            
            logger.info(
                "audio_uploaded",
                filename=file_path.name,
                server_id=result.get("id"),
                size=result.get("size"),
            )
            return True
    except requests.exceptions.RequestException as e:
        logger.error(
            "upload_failed",
            filename=file_path.name,
            error=str(e),
        )
        return False
    except Exception as e:
        logger.error(
            "upload_error",
            filename=file_path.name,
            error=str(e),
        )
        return False


def listen_forever(api_url: Optional[str] = None) -> None:
    """
    Основной цикл записи с VAD.
    
    Args:
        api_url: URL API сервера для автоотправки. Если None, используется из settings.
    """
    if api_url is None:
        api_url = settings.API_URL
    
    if not api_url:
        logger.warning("api_url_not_set", message="Auto-upload disabled, files will be saved locally only")
    
    sample_rate = settings.AUDIO_SAMPLE_RATE
    frame_ms = settings.AUDIO_FRAME_MS
    silence_limit = settings.AUDIO_SILENCE_LIMIT
    
    buffer: list[bytes] = []
    silence_time = 0.0
    frame_duration = frame_ms / 1000.0
    block_size = int(sample_rate * frame_duration)
    
    def callback(indata: np.ndarray, frames: int, time_info, status) -> None:
        """Callback для обработки аудио потока."""
        nonlocal buffer, silence_time
        
        if status:
            logger.warning("audio_status", status=status)
        
        # Конвертируем в PCM (16-bit signed integer)
        pcm = (indata * 32768).astype(np.int16).tobytes()
        
        # Проверяем наличие речи
        is_speech = vad.is_speech(pcm, sample_rate)
        
        if is_speech:
            buffer.append(pcm)
            silence_time = 0.0
            logger.debug("speech_detected", buffer_frames=len(buffer))
        elif buffer:
            # Есть буфер, но речи нет
            silence_time += frame_duration
            buffer.append(pcm)  # Добавляем тишину в конец для естественности
            
            if silence_time >= silence_limit:
                # Достаточно тишины - проверяем сегмент фильтром
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                
                # Конвертируем PCM байты в numpy array для фильтрации
                audio_array = None
                should_skip = False
                
                if settings.FILTER_MUSIC and len(buffer) > 0:
                    try:
                        # Объединяем все PCM кадры в один массив
                        pcm_bytes = b"".join(buffer)
                        # Конвертируем в numpy array (int16 -> float32)
                        audio_int16 = np.frombuffer(pcm_bytes, dtype=np.int16)
                        audio_array = audio_int16.astype(np.float32) / 32768.0
                        
                        # Применяем фильтр
                        should_skip, filter_metrics = speech_filter.filter_segment(audio_array)
                        
                        if should_skip:
                            logger.info(
                                "segment_filtered_out",
                                reason=filter_metrics.get("reason", "unknown"),
                                speech_ratio=filter_metrics.get("speech_ratio"),
                                high_freq_ratio=filter_metrics.get("high_freq_ratio"),
                            )
                    except Exception as e:
                        logger.warning(
                            "filter_check_failed",
                            error=str(e),
                            message="Proceeding without filter check",
                        )
                        # При ошибке фильтрации продолжаем работу (fail-safe)
                        should_skip = False
                
                # Пропускаем сегмент если фильтр определил, что это не речь
                if should_skip:
                    buffer = []
                    silence_time = 0.0
                    return  # Возвращаемся из callback, пропуская этот сегмент
                
                # Сохраняем сегмент
                filename = settings.RECORDINGS_PATH / f"{timestamp}.wav"
                
                try:
                    write_wave(filename, buffer, sample_rate)
                    logger.info(
                        "segment_saved",
                        filename=filename.name,
                        frames=len(buffer),
                        duration_approx=f"{len(buffer) * frame_duration:.2f}s",
                    )
                    
                    # Автоотправка на сервер
                    if settings.EDGE_AUTO_UPLOAD and api_url:
                        success = upload_audio(filename, api_url)
                        if success and settings.EDGE_DELETE_AFTER_UPLOAD:
                            filename.unlink()
                            logger.debug("local_file_deleted", filename=filename.name)
                except Exception as e:
                    logger.error(
                        "save_failed",
                        filename=filename.name,
                        error=str(e),
                    )
                
                # Сбрасываем буфер
                buffer = []
                silence_time = 0.0
    
    # Начинаем запись
    logger.info(
        "listener_starting",
        sample_rate=sample_rate,
        frame_ms=frame_ms,
        silence_limit=silence_limit,
        auto_upload=settings.EDGE_AUTO_UPLOAD,
        api_url=api_url if api_url else "disabled",
        speech_filter_enabled=settings.FILTER_MUSIC,
        filter_method=settings.FILTER_METHOD,
    )
    
    try:
        with sd.RawInputStream(
            samplerate=sample_rate,
            blocksize=block_size,
            dtype="float32",
            channels=1,
            callback=callback,
        ):
            logger.info("listener_active", message="Listening for speech...")
            while True:
                time.sleep(0.1)
    except KeyboardInterrupt:
        logger.info("listener_stopped", message="Stopped by user")
    except Exception as e:
        logger.error("listener_error", error=str(e))
        raise


if __name__ == "__main__":
    import sys
    
    # Можно передать API URL как аргумент
    api_url_arg = sys.argv[1] if len(sys.argv) > 1 else None
    
    listen_forever(api_url=api_url_arg)

