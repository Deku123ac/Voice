$ErrorActionPreference = "Stop"

$runtimeRoot = "D:\AutoTTS_XTTS"
$python39 = Join-Path $env:LOCALAPPDATA "Programs\Python\Python39\python.exe"
$python311 = Join-Path $env:LOCALAPPDATA "Programs\Python\Python311\python.exe"

if (Test-Path $python39) {
    $pythonExe = $python39
} elseif (Test-Path $python311) {
    $pythonExe = $python311
} else {
    throw "Khong tim thay Python 3.9 hoac 3.11. Hay cai Python truoc."
}

$venvPath = Join-Path $runtimeRoot ".venv"
$venvPython = Join-Path $venvPath "Scripts\python.exe"

New-Item -ItemType Directory -Force -Path $runtimeRoot | Out-Null

if (!(Test-Path $venvPython)) {
    & $pythonExe -m venv $venvPath
}

& $venvPython -m pip install --upgrade pip setuptools wheel
& $venvPython -m pip install --index-url https://download.pytorch.org/whl/cpu torch torchaudio
& $venvPython -m pip install "TTS==0.22.0" pydub soundfile

& $venvPython -c "import torch; from TTS.api import TTS; print('XTTS runtime OK'); print('CUDA:', torch.cuda.is_available())"
