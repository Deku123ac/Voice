import importlib
import sys
import traceback


TESTS = [
    ("PySide6", "PySide6.QtWidgets", "QApplication"),
    ("edge-tts", "edge_tts", None),
    ("pydub", "pydub", "AudioSegment"),
    ("gTTS", "gtts", "gTTS"),
    ("certifi", "certifi", None),
    ("Piper", "piper", "PiperVoice"),
]


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    failed = False
    for label, module_name, attribute in TESTS:
        try:
            module = importlib.import_module(module_name)
            if attribute:
                getattr(module, attribute)
            print(f"{label} OK")
        except Exception:
            failed = True
            print(f"{label} ERROR", file=sys.stderr)
            traceback.print_exc()
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
