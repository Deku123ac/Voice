import argparse
import sys
import tempfile
import wave
from pathlib import Path
from typing import Optional


RUNTIME_ROOT = Path(r"D:\AutoTTS_OpenVoice")
OPENVOICE_ROOT = RUNTIME_ROOT / "OpenVoice"
CONVERTER_DIR = OPENVOICE_ROOT / "checkpoints" / "converter"


def prepare_wav(
    source: Path, destination: Path, max_ms: Optional[int] = None
) -> None:
    from pydub import AudioSegment
    from pydub.silence import detect_nonsilent

    audio = AudioSegment.from_file(source).set_channels(1).set_frame_rate(22050)
    if audio.sample_width != 2:
        audio = audio.set_sample_width(2)
    audio = audio.high_pass_filter(80).low_pass_filter(7500)

    silence_threshold = max(-42, int(audio.dBFS - 18)) if audio.dBFS != float("-inf") else -42
    ranges = detect_nonsilent(
        audio,
        min_silence_len=250,
        silence_thresh=silence_threshold,
        seek_step=10,
    )
    if ranges:
        combined = AudioSegment.silent(duration=0, frame_rate=22050)
        kept_ms = 0
        for start, end in ranges:
            clip = audio[max(0, start - 60) : min(len(audio), end + 100)]
            if len(clip) < 250:
                continue
            if kept_ms:
                combined += AudioSegment.silent(duration=80, frame_rate=22050)
            if max_ms and kept_ms + len(clip) > max_ms:
                clip = clip[: max_ms - kept_ms]
            combined += clip
            kept_ms += len(clip)
            if max_ms and kept_ms >= max_ms:
                break
        if len(combined) >= 500:
            audio = combined
    if max_ms:
        audio = audio[:max_ms]
    audio.export(destination, format="wav")


def main() -> int:
    parser = argparse.ArgumentParser(description="OpenVoice CPU tone converter")
    parser.add_argument("--source", required=True)
    parser.add_argument("--reference", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    source = Path(args.source).resolve()
    reference = Path(args.reference).resolve()
    output = Path(args.output).resolve()
    if not source.is_file():
        raise FileNotFoundError(f"Không tìm thấy source audio: {source}")
    if not reference.is_file():
        raise FileNotFoundError(f"Không tìm thấy reference voice: {reference}")
    if not (CONVERTER_DIR / "config.json").exists():
        raise FileNotFoundError("Thiếu OpenVoice converter config.")
    if not (CONVERTER_DIR / "checkpoint.pth").exists():
        raise FileNotFoundError("Thiếu OpenVoice converter checkpoint.")

    sys.path.insert(0, str(OPENVOICE_ROOT))
    import torch
    from openvoice.api import OpenVoiceBaseClass, ToneColorConverter

    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="autotts_openvoice_") as temp_dir:
        temp = Path(temp_dir)
        source_wav = temp / "source.wav"
        reference_wav = temp / "reference.wav"
        prepare_wav(source, source_wav)
        prepare_wav(reference, reference_wav, max_ms=30000)

        # OpenVoice V1 truyền nhầm enable_watermark xuống lớp cha trên một số
        # bản Windows. Khởi tạo lớp cha trực tiếp để tắt watermark an toàn.
        converter = ToneColorConverter.__new__(ToneColorConverter)
        OpenVoiceBaseClass.__init__(
            converter,
            str(CONVERTER_DIR / "config.json"),
            device="cpu",
        )
        converter.watermark_model = None
        converter.version = getattr(converter.hps, "_version_", "v1")
        converter.load_ckpt(str(CONVERTER_DIR / "checkpoint.pth"))
        source_se = converter.extract_se([str(source_wav)])
        target_se = converter.extract_se([str(reference_wav)])
        converter.convert(
            audio_src_path=str(source_wav),
            src_se=source_se,
            tgt_se=target_se,
            output_path=str(output),
            message="@AutoTTS",
        )

    if not output.exists() or output.stat().st_size <= 44:
        raise RuntimeError("OpenVoice không tạo được audio hợp lệ.")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
