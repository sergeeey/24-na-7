"""
Триггерит транскрипцию для загруженного файла.

Читает file_id из файла и отправляет запрос на транскрипцию.
"""
import argparse
import sys
from pathlib import Path
import requests

from src.utils.logging import setup_logging, get_logger

setup_logging()
logger = get_logger("trigger_transcription")


def trigger_transcription(api_url: str, file_id: str) -> dict:
    """
    Запускает транскрипцию для файла.
    
    Args:
        api_url: URL API сервера (без trailing slash)
        file_id: ID файла для транскрипции
        
    Returns:
        Результат транскрипции
    """
    logger.info("triggering_transcription", api_url=api_url, file_id=file_id)
    
    try:
        response = requests.post(
            f"{api_url}/asr/transcribe",
            params={"file_id": file_id},
            timeout=120,  # Транскрипция может занимать время
        )
        
        response.raise_for_status()
        result = response.json()
        
        transcription = result.get("transcription", {})
        text = transcription.get("text", "")
        language = transcription.get("language", "unknown")
        
        logger.info(
            "transcription_completed",
            file_id=file_id,
            language=language,
            text_length=len(text),
        )
        
        print(f"✅ Transcription completed")
        print(f"   Language: {language}")
        print(f"   Text length: {len(text)} chars")
        if text:
            print(f"   Preview: {text[:100]}...")
        
        return result
        
    except requests.exceptions.RequestException as e:
        logger.error("transcription_failed", file_id=file_id, error=str(e))
        print(f"❌ Transcription failed: {e}", file=sys.stderr)
        raise


def main():
    """Точка входа для скрипта."""
    parser = argparse.ArgumentParser(description="Trigger transcription for uploaded file")
    parser.add_argument(
        "--url",
        default="http://localhost:8000",
        help="API server URL",
    )
    parser.add_argument(
        "--in",
        dest="input_file",
        type=Path,
        required=True,
        help="Input file with file_id",
    )
    
    args = parser.parse_args()
    
    # Читаем file_id
    if not args.input_file.exists():
        print(f"❌ Input file not found: {args.input_file}", file=sys.stderr)
        sys.exit(1)
    
    file_id = args.input_file.read_text(encoding="utf-8").strip()
    
    if not file_id:
        print(f"❌ Empty file_id in {args.input_file}", file=sys.stderr)
        sys.exit(1)
    
    try:
        result = trigger_transcription(args.url, file_id)
        sys.exit(0)
    except Exception as e:
        print(f"❌ Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()













