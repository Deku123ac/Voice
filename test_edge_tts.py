import sys
import traceback
from pathlib import Path

from app.tts_engines import EdgeTTSEngine


TEST_TEXT = "Xin chào, đây là kiểm tra giọng nói tiếng Việt."
TEST_CASES = [
    ("vi-VN-HoaiMyNeural", "test_hoaimy.mp3"),
    ("vi-VN-NamMinhNeural", "test_namminh.mp3"),
]


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    output_dir = Path(__file__).resolve().parent / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    failed = False

    for voice, filename in TEST_CASES:
        target = output_dir / filename
        print(f"Đang test {voice} -> {target}")
        try:
            engine = EdgeTTSEngine(
                voice=voice,
                speed=1.0,
                pitch=0,
                volume=100,
                retries=2,
                retry_delay=2.0,
                fallback_to_gtts=False,
                fallback_to_silent=False,
            )
            engine.generate(TEST_TEXT, target)
            if not target.exists() or target.stat().st_size == 0:
                raise RuntimeError(f"File test rỗng hoặc không tồn tại: {target}")
            print(
                f"OK: voice={engine.used_voice}, "
                f"size={target.stat().st_size} bytes"
            )
        except Exception:
            failed = True
            print(f"ERROR khi test voice {voice}", file=sys.stderr)
            traceback.print_exc()

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
