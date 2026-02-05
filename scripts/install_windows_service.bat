@echo off
REM Установка Reflexio Listener как службы Windows через NSSM
REM 
REM Требования:
REM 1. Скачать NSSM: https://nssm.cc/download
REM 2. Распаковать и добавить в PATH или указать полный путь
REM 3. Запустить этот скрипт от имени администратора

echo ========================================
echo Reflexio Listener - Windows Service Setup
echo ========================================
echo.

REM Проверка прав администратора
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo [ERROR] Запустите от имени администратора!
    pause
    exit /b 1
)

REM Пути (измените при необходимости)
set SERVICE_NAME=ReflexioListener
set PROJECT_DIR=%~dp0..
set VENV_DIR=%PROJECT_DIR%\venv
set PYTHON_EXE=%VENV_DIR%\Scripts\python.exe
set LISTENER_SCRIPT=%PROJECT_DIR%\src\edge\listener.py
set API_URL=http://127.0.0.1:8000

REM Проверка существования файлов
if not exist "%PYTHON_EXE%" (
    echo [ERROR] Python не найден: %PYTHON_EXE%
    echo        Убедитесь, что виртуальное окружение создано: python -m venv venv
    pause
    exit /b 1
)

if not exist "%LISTENER_SCRIPT%" (
    echo [ERROR] Listener script не найден: %LISTENER_SCRIPT%
    pause
    exit /b 1
)

REM Проверка NSSM
where nssm >nul 2>&1
if %errorLevel% neq 0 (
    echo [ERROR] NSSM не найден в PATH
    echo        Скачайте с https://nssm.cc/download и добавьте в PATH
    echo        Или укажите полный путь к nssm.exe ниже
    set /p NSSM_PATH="Путь к nssm.exe: "
    if not exist "%NSSM_PATH%" (
        echo [ERROR] NSSM не найден: %NSSM_PATH%
        pause
        exit /b 1
    )
) else (
    set NSSM_PATH=nssm
)

echo [INFO] Пути:
echo        Service: %SERVICE_NAME%
echo        Python: %PYTHON_EXE%
echo        Script: %LISTENER_SCRIPT%
echo        API URL: %API_URL%
echo.

REM Удаляем службу если уже существует
echo [INFO] Проверка существующей службы...
%NSSM_PATH% stop %SERVICE_NAME% >nul 2>&1
%NSSM_PATH% remove %SERVICE_NAME% confirm >nul 2>&1

REM Устанавливаем службу
echo [INFO] Установка службы...
%NSSM_PATH% install %SERVICE_NAME% "%PYTHON_EXE%"
if %errorLevel% neq 0 (
    echo [ERROR] Не удалось установить службу
    pause
    exit /b 1
)

REM Настройка параметров
echo [INFO] Настройка параметров...
%NSSM_PATH% set %SERVICE_NAME% AppParameters "\"%LISTENER_SCRIPT%\" %API_URL%"
%NSSM_PATH% set %SERVICE_NAME% AppDirectory "%PROJECT_DIR%"
%NSSM_PATH% set %SERVICE_NAME% DisplayName "Reflexio 24/7 Listener"
%NSSM_PATH% set %SERVICE_NAME% Description "Умный диктофон Reflexio 24/7 - запись речи с VAD"
%NSSM_PATH% set %SERVICE_NAME% Start SERVICE_AUTO_START
%NSSM_PATH% set %SERVICE_NAME% AppStdout "%PROJECT_DIR%\logs\listener_stdout.log"
%NSSM_PATH% set %SERVICE_NAME% AppStderr "%PROJECT_DIR%\logs\listener_stderr.log"

echo.
echo ========================================
echo Установка завершена!
echo ========================================
echo.
echo Для управления службой используйте:
echo   Запуск:   nssm start %SERVICE_NAME%
echo   Остановка: nssm stop %SERVICE_NAME%
echo   Удаление: nssm remove %SERVICE_NAME% confirm
echo.
echo Или через Services.msc (Панель управления)
echo.

REM Запускаем службу
set /p START_SERVICE="Запустить службу сейчас? (Y/N): "
if /i "%START_SERVICE%"=="Y" (
    echo [INFO] Запуск службы...
    %NSSM_PATH% start %SERVICE_NAME%
    if %errorLevel% equ 0 (
        echo [SUCCESS] Служба запущена!
    ) else (
        echo [ERROR] Не удалось запустить службу
    )
)

pause













