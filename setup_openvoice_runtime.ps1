$ErrorActionPreference = "Stop"

$runtimeRoot = "D:\AutoTTS_OpenVoice"
$python39 = Join-Path $env:LOCALAPPDATA "Programs\Python\Python39\python.exe"
$installer = Join-Path $env:TEMP "python-3.9.13-amd64.exe"
$repo = Join-Path $runtimeRoot "OpenVoice"
$venvPython = Join-Path $runtimeRoot ".venv\Scripts\python.exe"

New-Item -ItemType Directory -Force -Path $runtimeRoot | Out-Null

if (-not (Test-Path $python39)) {
    Write-Host "Dang tai Python 3.9..."
    Invoke-WebRequest `
        -Uri "https://www.python.org/ftp/python/3.9.13/python-3.9.13-amd64.exe" `
        -OutFile $installer
    Start-Process -FilePath $installer -ArgumentList @(
        "/quiet",
        "InstallAllUsers=0",
        "PrependPath=0",
        "Include_launcher=0",
        "Include_test=0",
        "SimpleInstall=1"
    ) -Wait
}

if (-not (Test-Path (Join-Path $repo ".git"))) {
    git clone --depth 1 https://github.com/myshell-ai/OpenVoice.git $repo
}

if (-not (Test-Path $venvPython)) {
    & $python39 -m venv (Join-Path $runtimeRoot ".venv")
}

& $venvPython -m pip install --upgrade pip setuptools wheel
& $venvPython -m pip install `
    torch==2.2.2 torchaudio==2.2.2 `
    --index-url https://download.pytorch.org/whl/cpu
& $venvPython -m pip install -e $repo --no-deps
& $venvPython -m pip install `
    numpy==1.26.4 librosa==0.10.2.post1 soundfile==0.12.1 `
    pydub==0.25.1 unidecode==1.3.8 inflect==7.3.1 `
    eng_to_ipa==0.0.2 pypinyin==0.50.0 cn2an==0.5.22 `
    jieba==0.42.1 langid==1.1.6 scipy==1.13.1

$converterDir = Join-Path $repo "checkpoints\converter"
New-Item -ItemType Directory -Force -Path $converterDir | Out-Null
$hfBase = "https://huggingface.co/myshell-ai/OpenVoice/resolve/main/checkpoints/converter"
if (-not (Test-Path (Join-Path $converterDir "config.json"))) {
    Invoke-WebRequest "$hfBase/config.json" `
        -OutFile (Join-Path $converterDir "config.json")
}
if (-not (Test-Path (Join-Path $converterDir "checkpoint.pth"))) {
    Invoke-WebRequest "$hfBase/checkpoint.pth" `
        -OutFile (Join-Path $converterDir "checkpoint.pth")
}

& $venvPython -c "import torch, librosa; from openvoice.api import ToneColorConverter; print('OpenVoice OK')"
