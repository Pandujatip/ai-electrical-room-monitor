@echo off
setlocal enabledelayedexpansion
title AI K3 ELECTRICAL ROOM MONITOR - RUNNING
color 0A

:: Cari Python yang valid
set PY_CMD=
if exist "venv\Scripts\python.exe" set "PY_CMD=venv\Scripts\python.exe"
if "%PY_CMD%"=="" if exist "C:\imou-yolo-venv\Scripts\python.exe" set "PY_CMD=C:\imou-yolo-venv\Scripts\python.exe"
if "%PY_CMD%"=="" if exist ".venv\Scripts\python.exe" set "PY_CMD=.venv\Scripts\python.exe"
if "%PY_CMD%"=="" set "PY_CMD=python"

echo ===============================================================================
echo        MENJALANKAN SISTEM AI MONITORING K3 DAN WHATSAPP BOT
echo ===============================================================================
echo [*] Python Engine: %PY_CMD%
echo.

:: 1. Jalankan WhatsApp Bridge
if exist "whatsapp-bridge\server.js" (
    start "WhatsApp Bridge Bot" /min cmd /c "cd /d whatsapp-bridge && node server.js"
)

:: 2. Buka Browser otomatis setelah delay 2 detik
start "" cmd /c "timeout /t 2 /nobreak >nul && start http://127.0.0.1:8000"

:: 3. Jalankan FastAPI Uvicorn
%PY_CMD% -m uvicorn app:app --host 0.0.0.0 --port 8000 --workers 1

pause
