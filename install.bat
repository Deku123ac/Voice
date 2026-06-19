@echo off
setlocal
cd /d "%~dp0"

py --version
if errorlevel 1 goto :error

if not exist "requirements.txt" (
  echo KHONG TIM THAY requirements.txt.
  goto :error
)

subst Z: "%CD%" >nul 2>nul
if errorlevel 1 goto :error

if not exist "Z:\.venv\Scripts\python.exe" (
  py -m venv Z:\.venv
  if errorlevel 1 goto :error_with_subst
)

set "VPY=Z:\.venv\Scripts\python.exe"
"%VPY%" -m pip install --upgrade pip
if errorlevel 1 goto :error_with_subst
"%VPY%" -m pip install -r Z:\requirements.txt
if errorlevel 1 goto :error_with_subst
"%VPY%" -m pip install --upgrade edge-tts certifi
if errorlevel 1 goto :error_with_subst

subst Z: /d
set "VPY=.venv\Scripts\python.exe"
"%VPY%" test_imports.py
if errorlevel 1 goto :error

echo.
echo CAI DAT THANH CONG.
pause
exit /b 0

:error_with_subst
subst Z: /d >nul 2>nul
:error
echo.
echo CAI DAT THAT BAI. Vui long doc thong bao ben tren.
pause
exit /b 1
