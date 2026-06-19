import shutil
import subprocess
import wave
from pathlib import Path

from .error_logger import log_exception


class MissingAudioDependencyError(RuntimeError):
    """Lỗi dependency audio có thể xử lý mà không đóng toàn bộ ứng dụng."""


def check_ffmpeg() -> tuple[bool, str]:
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg:
        return True, ffmpeg
    return (
        False,
        "Không tìm thấy ffmpeg. Hãy cài ffmpeg và mở lại ứng dụng.",
    )


def create_silent_audio(
    output_path: str | Path,
    duration_ms: int = 1500,
) -> Path:
    """Tạo silent MP3; nếu thiếu pydub/ffmpeg thì tạo WAV bằng thư viện chuẩn."""
    target = Path(output_path).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    duration_ms = max(250, int(duration_ms))

    try:
        from pydub import AudioSegment

        AudioSegment.silent(duration=duration_ms).export(target, format="mp3")
        return target
    except Exception as pydub_error:
        log_exception(
            "app.audio_utils.create_silent_audio.pydub",
            pydub_error,
            {"output_path": target, "duration_ms": duration_ms},
        )

    ok, ffmpeg = check_ffmpeg()
    if ok:
        try:
            subprocess.run(
                [
                    ffmpeg,
                    "-y",
                    "-f",
                    "lavfi",
                    "-i",
                    "anullsrc=r=24000:cl=mono",
                    "-t",
                    f"{duration_ms / 1000:.3f}",
                    "-q:a",
                    "9",
                    str(target),
                ],
                check=True,
                capture_output=True,
                text=True,
                timeout=60,
            )
            return target
        except Exception as ffmpeg_error:
            log_exception(
                "app.audio_utils.create_silent_audio.ffmpeg",
                ffmpeg_error,
                {"output_path": target, "duration_ms": duration_ms},
            )

    wav_target = target.with_suffix(".wav")
    try:
        sample_rate = 24000
        frame_count = round(sample_rate * duration_ms / 1000)
        with wave.open(str(wav_target), "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(sample_rate)
            wav_file.writeframes(b"\x00\x00" * frame_count)
        return wav_target
    except Exception as exc:
        log_exception(
            "app.audio_utils.create_silent_audio.wave",
            exc,
            {"output_path": wav_target, "duration_ms": duration_ms},
        )
        raise RuntimeError(f"Không thể tạo silent audio: {exc}") from exc


def join_mp3_files(
    output_dir: str | Path,
    destination: str | Path | None = None,
) -> Path:
    ok, message = check_ffmpeg()
    if not ok:
        raise RuntimeError(message)
    try:
        from pydub import AudioSegment
    except ImportError as exc:
        log_exception("app.audio_utils.join_mp3_files.import", exc)
        raise MissingAudioDependencyError(
            "Thiếu pydub nên chưa thể nối MP3. "
            "Hãy chạy run.bat hoặc install.bat."
        ) from exc

    folder = Path(output_dir)
    files = sorted(
        (
            item
            for item in folder.glob("*.mp3")
            if item.name.lower() != "final_joined.mp3"
        ),
        key=lambda item: (
            int(item.stem) if item.stem.isdigit() else 10**12,
            item.name.lower(),
        ),
    )
    if not files:
        raise ValueError("Không có file MP3 riêng lẻ nào để nối.")

    combined = AudioSegment.empty()
    for file_path in files:
        try:
            combined += AudioSegment.from_mp3(file_path)
        except Exception as exc:
            log_exception(
                "app.audio_utils.join_mp3_files.decode",
                exc,
                {"file": file_path},
            )
            raise RuntimeError(
                f"Không thể đọc {file_path.name}; file có thể rỗng hoặc hỏng."
            ) from exc
    target = Path(destination) if destination else folder / "final_joined.mp3"
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        combined.export(target, format="mp3")
    except Exception as exc:
        log_exception(
            "app.audio_utils.join_mp3_files.export",
            exc,
            {"destination": target},
        )
        raise
    return target
