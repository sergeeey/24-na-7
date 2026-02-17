#!/usr/bin/env python3
"""
Reflexio Edge Listener — Автономная версия

Запускает "умный диктофон" без установки всего проекта.
Всё в одном файле, создаёт .env автоматически, работает из любой директории.

Использование:
    python listener_standalone.py [API_URL]

Пример:
    python listener_standalone.py http://localhost:8000
    python listener_standalone.py https://your-server.com
"""

import sys
import os
import wave
import time
import json
from pathlib import Path
from datetime import datetime
from typing import Optional

# Попытка импорта зависимостей
try:
    import webrtcvad
    import sounddevice as sd
    import numpy as np
    import requests
except ImportError as e:
    print(f"❌ Ошибка: не установлены зависимости: {e}")
    print("\nУстановите зависимости:")
    print("  pip install webrtcvad sounddevice numpy requests")
    sys.exit(1)


# ============================================================================
# Конфигурация
# ============================================================================

class Config:
    """Простая конфигурация."""
    
    def __init__(self):
        self.work_dir = Path.cwd()
        self.env_file = self.work_dir / ".env.reflexio"
        self.recordings_dir = self.work_dir / "recordings"
        self.log_file = self.work_dir / "listener.log"
        
        # Значения по умолчанию
        self.api_url = "http://localhost:8000"
        self.sample_rate = 16000
        self.frame_ms = 30
        self.silence_limit = 2.0
        self.vad_aggressiveness = 2
        self.auto_upload = True
        self.delete_after_upload = True
        
        # Загружаем из .env или создаём
        self.load_or_create_env()
        
        # Создаём директории
        self.recordings_dir.mkdir(parents=True, exist_ok=True)
    
    def load_or_create_env(self):
        """Загружает .env или создаёт новый."""
        if self.env_file.exists():
            self.load_env()
        else:
            self.create_env()
    
    def load_env(self):
        """Загружает настройки из .env."""
        try:
            with open(self.env_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    if "=" in line:
                        key, value = line.split("=", 1)
                        key = key.strip()
                        value = value.strip().strip('"').strip("'")
                        
                        if key == "API_URL":
                            self.api_url = value
                        elif key == "AUDIO_SAMPLE_RATE":
                            self.sample_rate = int(value)
                        elif key == "AUDIO_SILENCE_LIMIT":
                            self.silence_limit = float(value)
                        elif key == "AUDIO_VAD_AGGRESSIVENESS":
                            self.vad_aggressiveness = int(value)
                        elif key == "EDGE_AUTO_UPLOAD":
                            self.auto_upload = value.lower() == "true"
                        elif key == "EDGE_DELETE_AFTER_UPLOAD":
                            self.delete_after_upload = value.lower() == "true"
            
            self.log(f"✅ Загружены настройки из {self.env_file}")
        except Exception as e:
            self.log(f"⚠️  Ошибка загрузки .env: {e}, используем значения по умолчанию")
    
    def create_env(self):
        """Создаёт новый .env файл."""
        env_content = f"""# Reflexio Edge Listener - Auto-generated config
# Измените значения при необходимости

API_URL={self.api_url}
AUDIO_SAMPLE_RATE={self.sample_rate}
AUDIO_FRAME_MS={self.frame_ms}
AUDIO_SILENCE_LIMIT={self.silence_limit}
AUDIO_VAD_AGGRESSIVENESS={self.vad_aggressiveness}
EDGE_AUTO_UPLOAD={str(self.auto_upload).lower()}
EDGE_DELETE_AFTER_UPLOAD={str(self.delete_after_upload).lower()}
"""
        try:
            with open(self.env_file, "w", encoding="utf-8") as f:
                f.write(env_content)
            self.log(f"✅ Создан файл конфигурации: {self.env_file}")
        except Exception as e:
            self.log(f"⚠️  Не удалось создать .env: {e}")
    
    def log(self, message: str, level: str = "INFO"):
        """Логирует сообщение в консоль и файл."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_message = f"[{timestamp}] [{level}] {message}"
        
        print(log_message)
        
        try:
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(log_message + "\n")
        except Exception:
            pass


# ============================================================================
# Audio Recording & VAD
# ============================================================================

class VoiceRecorder:
    """Класс для записи речи с VAD."""
    
    def __init__(self, config: Config):
        self.config = config
        self.vad = webrtcvad.Vad(config.vad_aggressiveness)
        self.buffer: list[bytes] = []
        self.silence_time = 0.0
        self.frame_duration = config.frame_ms / 1000.0
        self.block_size = int(config.sample_rate * self.frame_duration)
        
        self.config.log(f"Инициализация VoiceRecorder: SR={config.sample_rate}Hz, VAD={config.vad_aggressiveness}")
    
    def write_wave(self, path: Path, audio_frames: list[bytes]) -> None:
        """Записывает аудио в WAV файл."""
        with wave.open(str(path), "wb") as wf:
            wf.setnchannels(1)  # Моно
            wf.setsampwidth(2)  # 16-bit
            wf.setframerate(self.config.sample_rate)
            wf.writeframes(b"".join(audio_frames))
    
    def upload_audio(self, file_path: Path) -> bool:
        """Отправляет аудиофайл на сервер."""
        if not self.config.auto_upload:
            self.config.log(f"Автоотправка отключена, файл сохранён: {file_path}")
            return False
        
        try:
            with open(file_path, "rb") as f:
                files = {"file": (file_path.name, f, "audio/wav")}
                response = requests.post(
                    f"{self.config.api_url}/ingest/audio",
                    files=files,
                    timeout=30,
                )
            response.raise_for_status()
            result = response.json()
            
            self.config.log(
                f"✅ Файл отправлен: {file_path.name} → сервер (ID: {result.get('id', 'unknown')})",
                "SUCCESS"
            )
            return True
        except requests.exceptions.RequestException as e:
            self.config.log(f"❌ Ошибка отправки {file_path.name}: {e}", "ERROR")
            return False
        except Exception as e:
            self.config.log(f"❌ Неожиданная ошибка: {e}", "ERROR")
            return False
    
    def callback(self, indata: np.ndarray, frames: int, time_info, status) -> None:
        """Callback для обработки аудио потока."""
        if status:
            self.config.log(f"Audio status: {status}", "WARNING")
        
        # Конвертируем в PCM (16-bit signed integer)
        pcm = (indata * 32768).astype(np.int16).tobytes()
        
        # Проверяем наличие речи
        is_speech = self.vad.is_speech(pcm, self.config.sample_rate)
        
        if is_speech:
            self.buffer.append(pcm)
            self.silence_time = 0.0
        elif self.buffer:
            # Есть буфер, но речи нет
            self.silence_time += self.frame_duration
            self.buffer.append(pcm)  # Добавляем тишину для естественности
            
            if self.silence_time >= self.config.silence_limit:
                # Достаточно тишины - сохраняем сегмент
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = self.config.recordings_dir / f"{timestamp}.wav"
                
                try:
                    self.write_wave(filename, self.buffer)
                    duration = len(self.buffer) * self.frame_duration
                    self.config.log(
                        f"🎤 Сегмент сохранён: {filename.name} ({duration:.1f}s)",
                        "INFO"
                    )
                    
                    # Автоотправка
                    if self.upload_audio(filename):
                        if self.config.delete_after_upload:
                            filename.unlink()
                            self.config.log(f"🗑️  Локальный файл удалён: {filename.name}")
                    
                except Exception as e:
                    self.config.log(f"❌ Ошибка сохранения: {e}", "ERROR")
                
                # Сбрасываем буфер
                self.buffer = []
                self.silence_time = 0.0
    
    def listen_forever(self) -> None:
        """Основной цикл записи."""
        self.config.log("=" * 60)
        self.config.log("Reflexio Edge Listener — Автономная версия")
        self.config.log("=" * 60)
        self.config.log(f"API URL: {self.config.api_url}")
        self.config.log(f"Запись: {self.config.sample_rate}Hz, VAD={self.config.vad_aggressiveness}")
        self.config.log(f"Автоотправка: {'✅' if self.config.auto_upload else '❌'}")
        self.config.log("=" * 60)
        self.config.log("🎧 Слушаю микрофон... (Ctrl+C для остановки)")
        self.config.log("")
        
        try:
            with sd.RawInputStream(
                samplerate=self.config.sample_rate,
                blocksize=self.block_size,
                dtype="float32",
                channels=1,
                callback=self.callback,
            ):
                while True:
                    time.sleep(0.1)
        except KeyboardInterrupt:
            self.config.log("")
            self.config.log("⏹️  Остановка...", "INFO")
        except Exception as e:
            self.config.log(f"❌ Критическая ошибка: {e}", "ERROR")
            raise


# ============================================================================
# Main
# ============================================================================

def main():
    """Точка входа."""
    # Проверяем API URL в аргументах
    api_url = None
    if len(sys.argv) > 1:
        api_url = sys.argv[1]
    
    # Создаём конфигурацию
    config = Config()
    
    # Переопределяем API URL если передан аргумент
    if api_url:
        config.api_url = api_url
        config.log(f"API URL из аргументов: {api_url}")
    
    # Проверяем доступность API (опционально)
    if config.auto_upload:
        try:
            response = requests.get(f"{config.api_url}/health", timeout=5)
            if response.status_code == 200:
                config.log(f"✅ API сервер доступен: {config.api_url}")
            else:
                config.log(f"⚠️  API сервер ответил с кодом {response.status_code}", "WARNING")
        except requests.exceptions.RequestException:
            config.log(
                f"⚠️  API сервер недоступен: {config.api_url}",
                "WARNING"
            )
            config.log("   Запись будет продолжаться, но отправка может не работать", "WARNING")
    
    # Проверяем микрофон
    try:
        devices = sd.query_devices()
        default_input = sd.default.device[0]
        if default_input is not None:
            device_info = devices[default_input]
            config.log(f"🎤 Микрофон: {device_info['name']}")
        else:
            config.log("⚠️  Устройство ввода не найдено", "WARNING")
    except Exception as e:
        config.log(f"⚠️  Не удалось получить информацию о микрофоне: {e}", "WARNING")
    
    # Запускаем запись
    try:
        recorder = VoiceRecorder(config)
        recorder.listen_forever()
    except Exception as e:
        config.log(f"❌ Ошибка запуска: {e}", "ERROR")
        sys.exit(1)


if __name__ == "__main__":
    main()













