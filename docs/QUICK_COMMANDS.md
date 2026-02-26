# Reflexio 24/7 — Шпаргалка команд

## ⚡ Самый быстрый старт (1 минута)

```bash
# 1. Установка
pip install -e ".[dev]"
cp .env.example .env

# 2. Терминал 1: API сервер
uvicorn src.api.main:app --reload

# 3. Терминал 2: Listener
python src/edge/listener.py http://127.0.0.1:8000
```

Готово! Говори в микрофон → файлы автоматически отправляются на сервер.

---

## 📦 Автономный режим (без установки проекта)

```bash
# Установи зависимости один раз
pip install webrtcvad sounddevice numpy requests

# Запусти listener
python listener_standalone.py http://your-server:8000
```

---

## 🔧 Основные команды

### API сервер
```bash
# Обычный запуск
uvicorn src.api.main:app --reload

# На конкретном порту
uvicorn src.api.main:app --host 0.0.0.0 --port 8000

# В фоне (Linux/macOS)
nohup uvicorn src.api.main:app --host 0.0.0.0 --port 8000 > logs/api.log 2>&1 &
```

### Listener (диктофон)
```bash
# Обычный запуск
python src/edge/listener.py http://127.0.0.1:8000

# В фоне (Linux/macOS)
nohup python src/edge/listener.py http://127.0.0.1:8000 > listener.log 2>&1 &

# Автономный режим
python listener_standalone.py http://your-server:8000
```

### Тестирование
```bash
# Health check
curl http://127.0.0.1:8000/health

# Smoke-тест (загрузка тестового файла)
python scripts/smoke_ingest.py --url http://127.0.0.1:8000

# Транскрипция
python scripts/trigger_transcription.py --url http://127.0.0.1:8000 --in sample_file_id.txt

# Все тесты
pytest
```

### Утилиты
```bash
# Инициализация БД
python scripts/db_init.py schema.sql

# Метрики
python scripts/metrics_snapshot.py

# Полная сборка
@playbook build-reflexio
```

---

## 🚀 Фоновый режим (24/7)

### Linux (systemd)

```bash
# Скопировать service файл
sudo cp reflexio-listener.service /etc/systemd/system/

# Отредактировать пути
sudo nano /etc/systemd/system/reflexio-listener.service

# Включить и запустить
sudo systemctl daemon-reload
sudo systemctl enable reflexio-listener
sudo systemctl start reflexio-listener

# Проверка
sudo systemctl status reflexio-listener
sudo journalctl -u reflexio-listener -f
```

### Windows (NSSM)

```bash
# Запустить от имени администратора
scripts\install_windows_service.bat

# Или вручную через NSSM GUI
nssm install ReflexioListener
```

---

## 📊 Мониторинг

```bash
# Логи API
tail -f logs/api.log

# Логи listener
tail -f listener.log

# Метрики
cat cursor-metrics.json

# Статус API
curl http://127.0.0.1:8000/health
```

---

## 🐛 Проблемы?

### "No module named 'webrtcvad'"
```bash
pip install webrtcvad sounddevice numpy requests
```

### "Connection refused"
- Проверь, что API сервер запущен: `curl http://127.0.0.1:8000/health`
- Проверь `API_URL` в `.env`

### Микрофон не работает
- Linux: проверь `pulseaudio` или `alsa`
- Windows: настройки приватности → Микрофон
- macOS: настройки системы → Конфиденциальность → Микрофон

---

## 📖 Полная документация

- [QUICKSTART.md](QUICKSTART.md) — детальная инструкция
- [README.md](README.md) — общая документация













