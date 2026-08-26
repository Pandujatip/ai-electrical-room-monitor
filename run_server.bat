@echo off
cd /d "%~dp0"
if not exist ".env" (
  echo File .env belum ada. Salin .env.example menjadi .env lalu isi URL RTSP.
  pause
  exit /b 1
)
echo Starting Imou Electrical Room Monitor at http://127.0.0.1:8000
if not exist "C:\imou-yolo-venv\Scripts\python.exe" (
  echo YOLO environment tidak ditemukan di C:\imou-yolo-venv
  echo Jalankan instalasi Ultralytics terlebih dahulu.
  pause
  exit /b 1
)
"C:\imou-yolo-venv\Scripts\python.exe" -m uvicorn app:app --host 127.0.0.1 --port 8000
