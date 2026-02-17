"""
Smoke-тест для ingest endpoint.

Создаёт тестовый WAV файл и отправляет его на сервер.
"""
import argparse
import sys
import tempfile
import wave
from pathlib import Path
import requests

from src.utils.logging import setup_logging, get_logger

setup_logging()
logger = get_logger("smoke_ingest")


def create_test_wav(duration: float = 0.5, sample_rate: int = 16000) -> Path:
    """
    Создаёт тестовый WAV файл с синусоидальным сигналом.
    
    Args:
        duration: Длительность в секундах
        sample_rate: Частота дискретизации
        
    Returns:
        Путь к созданному файлу
    """
    import numpy as np
    
    # Генерируем синусоиду (440 Hz - нота A)
    t = np.linspace(0, duration, int(sample_rate * duration))
    frequency = 440.0
    audio_data = (np.sin(2 * np.pi * frequency * t) * 32767).astype(np.int16)
    
    # Сохраняем во временный файл
    tmp_file = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    tmp_path = Path(tmp_file.name)
    tmp_file.close()
    
    with wave.open(str(tmp_path), "wb") as wf:
        wf.setnchannels(1)  # Моно
        wf.setsampwidth(2)  # 16-bit
        wf.setframerate(sample_rate)
        wf.writeframes(audio_data.tobytes())
    
    return tmp_path


def smoke_test_ingest(api_url: str, output_file: Path | None = None) -> str:
    """
    Выполняет smoke-тест ingest endpoint.
    
    Args:
        api_url: URL API сервера (без trailing slash)
        output_file: Путь для сохранения file_id
        
    Returns:
        file_id загруженного файла
    """
    logger.info("smoke_test_starting", api_url=api_url)
    
    # Создаём тестовый файл
    test_wav = create_test_wav()
    logger.info("test_file_created", path=str(test_wav))
    
    try:
        # Отправляем на сервер
        with open(test_wav, "rb") as f:
            files = {"file": ("smoke_test.wav", f, "audio/wav")}
            response = requests.post(
                f"{api_url}/ingest/audio",
                files=files,
                timeout=10,
            )
        
        response.raise_for_status()
        result = response.json()
        
        file_id = result["id"]
        logger.info(
            "smoke_test_passed",
            file_id=file_id,
            filename=result.get("filename"),
            size=result.get("size"),
        )
        
        print(f"✅ Smoke test passed")
        print(f"   File ID: {file_id}")
        print(f"   Filename: {result.get('filename')}")
        print(f"   Size: {result.get('size')} bytes")
        
        # Сохраняем file_id в файл
        if output_file:
            output_file.write_text(file_id, encoding="utf-8")
            logger.info("file_id_saved", path=str(output_file))
        
        return file_id
        
    except requests.exceptions.RequestException as e:
        logger.error("smoke_test_failed", error=str(e))
        print(f"❌ Smoke test failed: {e}", file=sys.stderr)
        raise
    finally:
        # Удаляем временный файл
        test_wav.unlink()


def main():
    """Точка входа для скрипта."""
    parser = argparse.ArgumentParser(description="Smoke test for ingest endpoint")
    parser.add_argument(
        "--url",
        default="http://localhost:8000",
        help="API server URL",
    )
    parser.add_argument(
        "--out",
        type=Path,
        help="Output file for file_id",
    )
    
    args = parser.parse_args()
    
    try:
        file_id = smoke_test_ingest(args.url, args.out)
        sys.exit(0)
    except Exception as e:
        print(f"❌ Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()













