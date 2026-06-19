import subprocess
import sys
from pathlib import Path


RUNTIME_PYTHON = Path(r"D:\AutoTTS_OpenVoice\.venv\Scripts\python.exe")
RUNTIME_ROOT = Path(r"D:\AutoTTS_OpenVoice\OpenVoice")


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if not RUNTIME_PYTHON.exists():
        print("OpenVoice chưa cài. Hãy chạy install_openvoice.bat.")
        return 1
    checkpoint = RUNTIME_ROOT / "checkpoints" / "converter" / "checkpoint.pth"
    config = RUNTIME_ROOT / "checkpoints" / "converter" / "config.json"
    if not checkpoint.exists() or not config.exists():
        print("Thiếu checkpoint OpenVoice. Hãy chạy install_openvoice.bat.")
        return 1
    completed = subprocess.run(
        [
            str(RUNTIME_PYTHON),
            "-c",
            (
                "import torch, librosa; "
                "from openvoice.api import ToneColorConverter; "
                "print('OpenVoice runtime OK')"
            ),
        ],
        text=True,
        capture_output=True,
    )
    print(completed.stdout.strip())
    if completed.returncode != 0:
        print(completed.stderr)
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
