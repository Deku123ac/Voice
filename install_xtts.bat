@echo off
cd /d "%~dp0"

echo Dang cai XTTS Local runtime...
powershell -ExecutionPolicy Bypass -File "%~dp0setup_xtts_runtime.ps1"
if errorlevel 1 (
  echo.
  echo Cai XTTS that bai. Xem logs hoac thong bao ben tren.
  pause
  exit /b 1
)

echo.
echo XTTS runtime da san sang tai D:\AutoTTS_XTTS
pause
