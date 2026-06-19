import argparse
from pathlib import Path


SUPPORTED_LANGUAGES = {
    "en",
    "es",
    "fr",
    "de",
    "it",
    "pt",
    "pl",
    "tr",
    "ru",
    "nl",
    "cs",
    "ar",
    "zh-cn",
    "hu",
    "ko",
    "ja",
}


def main() -> int:
    parser = argparse.ArgumentParser(description="XTTS local helper")
    parser.add_argument("--text", required=True)
    parser.add_argument("--language", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--speed", type=float, default=1.0)
    parser.add_argument("--speaker-wav", action="append", dest="speaker_wavs")
    args = parser.parse_args()

    text = str(args.text).strip()
    language = str(args.language).strip().lower()
    output = Path(args.output).resolve()
    speaker_wavs = [Path(path).resolve() for path in (args.speaker_wavs or [])]

    if not text:
        raise ValueError("Text XTTS đang rỗng.")
    if language not in SUPPORTED_LANGUAGES:
        raise ValueError(
            f"Language '{language}' không được XTTS helper hỗ trợ."
        )
    if not speaker_wavs:
        raise ValueError("Chưa có speaker wav cho XTTS.")
    missing = [str(path) for path in speaker_wavs if not path.is_file()]
    if missing:
        raise FileNotFoundError("Thiếu speaker wav: " + ", ".join(missing))

    output.parent.mkdir(parents=True, exist_ok=True)

    import torch
    from TTS.api import TTS

    device = "cuda" if torch.cuda.is_available() else "cpu"
    tts = TTS("tts_models/multilingual/multi-dataset/xtts_v2", gpu=device == "cuda")
    try:
        tts = tts.to(device)
    except Exception:
        pass

    tts.tts_to_file(
        text=text,
        file_path=str(output),
        speaker_wav=[str(path) for path in speaker_wavs],
        language=language,
        speed=max(0.75, min(1.25, float(args.speed))),
        split_sentences=True,
    )

    if not output.exists() or output.stat().st_size == 0:
        raise RuntimeError("XTTS không tạo được file audio hợp lệ.")

    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
