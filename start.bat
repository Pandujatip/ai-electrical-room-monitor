@echo off
title AI K3 ELECTRICAL ROOM MONITOR - RUNNING
color 0A

if not exist "venv\Scripts\python.exe" (
    color 0C
    echo [X] Virtual environment belum ditemukan!
    echo Harap jalankan file: install.bat terlebih dahulu.
    pause
    exit /b 1
)

echo ===============================================================================
echo        MENJALANKAN SISTEM AI MONITORING K3 & WHATSAPP BOT BRIDGE
echo ===============================================================================
echo.

:: 1. Jalankan WhatsApp Bridge (Port 3001)
echo [*] Menjalankan WhatsApp Bot Bridge pada port 3001...
if exist "whatsapp-bridge\server.js" (
    start "WhatsApp Bridge Bot" /min cmd /c "cd /d whatsapp-bridge && node server.js"
)

:: 2. Buka Browser Otomatis
echo [*] Membuka Dashboard Web di browser...
start "" "http://127.0.0.1:8000"

:: 3. Jalankan Server FastAPI Uvicorn (Port 8000)
echo [*] Menjalankan Server Utama AI Video Analytics pada port 8000...
echo.
echo Dashboard Web: http://127.0.0.1:8000
echo (Tekan Ctrl + C pada jendela ini untuk menghentikan server)
echo.
venv\Scripts\python.exe -m uvicorn app:app --host 0.0.0.0 --port 8000 --workers 1

pause
