@echo off
title AI K3 ELECTRICAL ROOM MONITOR - RUNNING
color 0A

:: 1. DETEKSI PYTHON INTERPRETER / VIRTUAL ENVIRONMENT YANG VALID
set "PY_CMD="

if exist "venv\Scripts\python.exe" (
    venv\Scripts\python.exe -c "import ultralytics" >nul 2>&1
    if not errorlevel 1 set "PY_CMD=venv\Scripts\python.exe"
)

if "%PY_CMD%"=="" if exist "C:\imou-yolo-venv\Scripts\python.exe" (
    C:\imou-yolo-venv\Scripts\python.exe -c "import ultralytics" >nul 2>&1
    if not errorlevel 1 set "PY_CMD=C:\imou-yolo-venv\Scripts\python.exe"
)

if "%PY_CMD%"=="" if exist ".venv\Scripts\python.exe" (
    .venv\Scripts\python.exe -c "import ultralytics" >nul 2>&1
    if not errorlevel 1 set "PY_CMD=.venv\Scripts\python.exe"
)

if "%PY_CMD%"=="" (
    python -c "import ultralytics" >nul 2>&1
    if not errorlevel 1 set "PY_CMD=python"
)

if "%PY_CMD%"=="" (
    color 0C
    echo ===============================================================================
    echo [X] Modul AI (Ultralytics / YOLO / PyTorch) belum lengkap di environment ini!
    echo.
    echo Harap jalankan file: install.bat terlebih dahulu untuk menginstal modul otomatis.
    echo ===============================================================================
    echo.
    pause
    exit /b 1
)

echo ===============================================================================
echo        MENJALANKAN SISTEM AI MONITORING K3 & WHATSAPP BOT BRIDGE
echo ===============================================================================
echo [*] Menggunakan Python Engine: %PY_CMD%
echo.

:: 2. JALANKAN WHATSAPP BRIDGE (Port 3001)
echo [*] Menjalankan WhatsApp Bot Bridge pada port 3001...
if exist "whatsapp-bridge\server.js" (
    start "WhatsApp Bridge Bot" /min cmd /c "cd /d whatsapp-bridge && node server.js"
)

:: 3. JALANKAN SERVER UTAMA AI VIDEO ANALYTICS (Port 8000)
echo [*] Memulai Server AI Video Analytics pada port 8000...
echo.
echo ===============================================================================
echo Dashboard Web: http://127.0.0.1:8000
echo (Tekan Ctrl + C pada jendela ini untuk menghentikan server)
echo ===============================================================================
echo.

:: Buka browser otomatis setelah delay 2 detik
start /b cmd /c "timeout /t 2 /nobreak >nul && start http://127.0.0.1:8000"

%PY_CMD% -m uvicorn app:app --host 0.0.0.0 --port 8000 --workers 1

pause
