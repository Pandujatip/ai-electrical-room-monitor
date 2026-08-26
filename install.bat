@echo off
setlocal enabledelayedexpansion
title INSTALASI SISTEM AI MONITORING K3 - IMOU ELECTRICAL ROOM
color 0B

echo ===============================================================================
echo       SELAMAT DATANG DI INSTALASI OTOMATIS AI K3 ELECTRICAL ROOM MONITOR
echo ===============================================================================
echo.
echo Sedang memeriksa spesifikasi dan komponen PC Anda...
echo.

:: 1. CHECK PYTHON
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [!] Python belum terpasang di PC ini.
    echo [*] Sedang mengunduh dan memasang Python 3.12 secara otomatis...
    winget install Python.Python.3.12 --silent --accept-package-agreements --accept-source-agreements
    if %errorlevel% neq 0 (
        echo [X] Gagal memasang Python via winget.
        echo Harap unduh dan pasang Python 3.12 dari: https://www.python.org/downloads/
        echo PENTING: Centang "Add Python to PATH" saat instalasi!
        pause
        exit /b 1
    )
    echo [OK] Python berhasil dipasang. Silakan buka kembali file install.bat jika PATH belum aktif.
) else (
    for /f "tokens=*" %%i in ('python --version') do echo [OK] Terdeteksi %%i
)

:: 2. CHECK NODE.JS & NPM
node --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [!] Node.js belum terpasang di PC ini (dibutuhkan untuk Bot WhatsApp).
    echo [*] Sedang memasang Node.js LTS secara otomatis...
    winget install OpenJS.NodeJS.LTS --silent --accept-package-agreements --accept-source-agreements
    if %errorlevel% neq 0 (
        echo [X] Gagal memasang Node.js via winget.
        echo Harap unduh dan pasang Node.js LTS dari: https://nodejs.org/
        pause
        exit /b 1
    )
    echo [OK] Node.js berhasil dipasang.
) else (
    for /f "tokens=*" %%i in ('node --version') do echo [OK] Terdeteksi Node.js %%i
)

echo.
echo ===============================================================================
echo [1/3] Menyiapkan Virtual Environment Python (venv)...
echo ===============================================================================
if not exist "venv" (
    python -m venv venv
    if %errorlevel% neq 0 (
        echo [X] Gagal membuat virtual environment.
        pause
        exit /b 1
    )
)
echo [OK] Virtual environment siap.

echo.
echo ===============================================================================
echo [2/3] Mengunduh dan Memasang Modul AI & Dependencies (PyTorch, YOLO, OpenCV)...
echo ===============================================================================
echo Proses ini memerlukan koneksi internet beberapa saat...
call venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo [X] Gagal memasang dependensi Python. Periksa koneksi internet Anda.
    pause
    exit /b 1
)
echo [OK] Semua modul AI dan OpenCV berhasil terpasang!

echo.
echo ===============================================================================
echo [3/3] Memasang Modul WhatsApp Bridge (Baileys Node.js)...
echo ===============================================================================
if exist "whatsapp-bridge" (
    cd whatsapp-bridge
    call npm install
    cd ..
    echo [OK] Modul WhatsApp Bridge berhasil dipasang!
)

:: CREATE DIRECTORIES IF NOT EXIST
if not exist "snapshots" mkdir snapshots
if not exist "logs" mkdir logs
if not exist "known_faces" mkdir known_faces
if not exist "static\audio" mkdir static\audio

:: GENERATE DEFAULT AUDIO WARNINGS
if not exist "static\audio\warning_female.mp3" (
    echo [*] Menyiapkan file audio peringatan K3...
    venv\Scripts\python.exe -c "import edge_tts, asyncio; asyncio.run(edge_tts.Communicate('Bapak ganteng, jangan lupa APD nya di pakai ya', 'id-ID-GadisNeural').save('static/audio/warning_female.mp3'))" >nul 2>&1
)
if not exist "static\audio\smoking_warning.mp3" (
    echo [*] Menyiapkan file audio peringatan larangan merokok...
    venv\Scripts\python.exe -c "import edge_tts, asyncio; asyncio.run(edge_tts.Communicate('Peringatan! Dilarang merokok di Ruang Elektrikal!', 'id-ID-GadisNeural').save('static/audio/smoking_warning.mp3'))" >nul 2>&1
)

color 0A
echo.
echo ===============================================================================
echo                       INSTALASI BERHASIL 100%%!
echo ===============================================================================
echo.
echo Sistem AI Monitoring Ruang Elektrikal siap digunakan di PC ini!
echo.
echo CARA MENJALANKAN:
echo Cukup klik dua kali (Double-Click) file: start.bat
echo Browser akan otomatis terbuka di: http://127.0.0.1:8000
echo.
echo ===============================================================================
pause
