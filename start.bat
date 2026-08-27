@echo off
title AI K3 ELECTRICAL ROOM MONITOR - RUNNING
color 0A

:: 1. DETEKSI PYTHON INTERPRETER / VIRTUAL ENVIRONMENT
set "PY_CMD="
if exist "venv\Scripts\python.exe" (
    set "PY_CMD=venv\Scripts\python.exe"
) else if exist ".venv\Scripts\python.exe" (
    set "PY_CMD=.venv\Scripts\python.exe"
) else if exist "C:\imou-yolo-venv\Scripts\python.exe" (
    set "PY_CMD=C:\imou-yolo-venv\Scripts\python.exe"
) else (
    python --version >nul 2>&1
    if %errorlevel% equ 0 (
        set "PY_CMD=python"
    )
)

if "%PY_CMD%"=="" (
    color 0C
    echo [X] Python / Virtual Environment belum ditemukan!
    echo Harap jalankan file: install.bat terlebih dahulu.
    echo.
    pause
    exit /b 1
)

echo ===============================================================================
echo        MENJALANKAN SISTEM AI MONITORING K3 & WHATSAPP BOT BRIDGE
echo ===============================================================================
echo [*] Menggunakan Python: %PY_CMD%
echo.

:: 2. JALANKAN WHATSAPP BRIDGE (Port 3001)
echo [*] Menjalankan WhatsApp Bot Bridge pada port 3001...
if exist "whatsapp-bridge\server.js" (
    start "WhatsApp Bridge Bot" /min cmd /c "cd /d whatsapp-bridge && node server.js"
)

:: 3. BUKA BROWSER OTOMATIS
echo [*] Membuka Dashboard Web di browser...
start "" "http://127.0.0.1:8000"

:: 4. JALANKAN SERVER UTAMA AI VIDEO ANALYTICS (Port 8000)
echo [*] Menjalankan Server Utama AI Video Analytics pada port 8000...
echo.
echo ===============================================================================
echo Dashboard Web: http://127.0.0.1:8000
echo (Tekan Ctrl + C pada jendela ini untuk menghentikan server)
echo ===============================================================================
echo.
%PY_CMD% -m uvicorn app:app --host 0.0.0.0 --port 8000 --workers 1

pause
