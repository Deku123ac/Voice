@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo Chua co .venv. Hay chay install.bat truoc.
  pause
  exit /b 1
)

".venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean --windowed --name "DaniAutoTTSStudio" --add-data "config.json;." main.py
if errorlevel 1 (
  echo Build that bai.
  pause
  exit /b 1
)
echo Da build xong tai thu muc dist\DaniAutoTTSStudio
pause
