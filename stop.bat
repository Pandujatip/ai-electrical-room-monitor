@echo off
title SHUTDOWN AI K3 MONITOR
color 0E

echo ===============================================================================
echo            MENGHENTIKAN SEMUA LAYANAN AI MONITORING & WHATSAPP
echo ===============================================================================
echo.

echo [*] Menghentikan Uvicorn (Port 8000)...
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":8000" ^| findstr "LISTENING"') do (
    taskkill /F /PID %%a >nul 2>&1
)

echo [*] Menghentikan WhatsApp Bridge (Port 3001)...
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":3001" ^| findstr "LISTENING"') do (
    taskkill /F /PID %%a >nul 2>&1
)

echo [OK] Semua layanan berhasil dihentikan.
echo.
pause
