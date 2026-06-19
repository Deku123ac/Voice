import asyncio
import re
import subprocess
import sys
import threading
import time
import traceback
import unicodedata
import wave
from pathlib import Path
from typing import Any, Coroutine

from .audio_utils import create_silent_audio
from .error_logger import log_exception
from .piper_manager import get_piper_voice
from .voice_library import get_reference_audio_files, get_reference_voice
from .utils import split_long_text


DEFAULT_EDGE_VOICE = "vi-VN-HoaiMyNeural"
SECONDARY_VI_VOICE = "vi-VN-NamMinhNeural"
DEFAULT_EDGE_VOICES = [
    DEFAULT_EDGE_VOICE,
    SECONDARY_VI_VOICE,
]
MAX_EDGE_CHUNK_LENGTH = 350
_VOICE_CACHE: set[str] | None = None


def sanitize_tts_text(value: Any) -> str:
    """Chuẩn hóa nội dung trước khi gửi TTS."""
    if value is None:
        return ""
    if isinstance(value, (list, tuple, set)):
        value = " ".join(str(item) for item in value if item is not None)
    text = unicodedata.normalize("NFKC", str(value))
    text = text.replace("\x00", "").replace("\r", " ").replace("\n", " ")
    text = "".join(char for char in text if unicodedata.category(char) != "Cc")
    return re.sub(r"\s+", " ", text).strip()


def run_async_safely(coro: Coroutine[Any, Any, Any]) -> Any:
    """Chạy coroutine bằng event loop mới, an toàn trong QThread."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        try:
            asyncio.set_event_loop(loop)
            return loop.run_until_complete(coro)
        finally:
            loop.run_until_complete(loop.shutdown_asyncgens())
            asyncio.set_event_loop(None)
            loop.close()

    result: dict[str, Any] = {}
    error: dict[str, BaseException] = {}

    def runner() -> None:
        loop = asyncio.new_event_loop()
        try:
            asyncio.set_event_loop(loop)
            result["value"] = loop.run_until_complete(coro)
        except BaseException as exc:
            error["exception"] = exc
        finally:
            loop.run_until_complete(loop.shutdown_asyncgens())
            asyncio.set_event_loop(None)
            loop.close()

    thread = threading.Thread(target=runner, name="EdgeTTSLoop", daemon=True)
    thread.start()
    thread.join()
    if "exception" in error:
        raise error["exception"]
    return result.get("value")


def load_edge_voices() -> list[dict[str, str]]:
    """Tải voice Edge và cập nhật cache dùng để kiểm tra voice."""
    global _VOICE_CACHE
    try:
        import edge_tts

        voices = run_async_safely(edge_tts.list_voices())
        result = [
            {
                "name": f"{voice['ShortName']} — {voice.get('Gender', '')}",
                "voice_id": voice["ShortName"],
            }
            for voice in voices
            if voice.get("ShortName")
            and voice.get("Locale") == "vi-VN"
        ]
        result.sort(key=lambda item: item["voice_id"])
        _VOICE_CACHE = {item["voice_id"] for item in result}
        return result
    except Exception:
        _VOICE_CACHE = set(DEFAULT_EDGE_VOICES)
        return [{"name": voice, "voice_id": voice} for voice in DEFAULT_EDGE_VOICES]


def available_voice_ids() -> set[str]:
    global _VOICE_CACHE
    if _VOICE_CACHE is None:
        load_edge_voices()
    return _VOICE_CACHE or set(DEFAULT_EDGE_VOICES)


class EdgeTTSEngine:
    def __init__(
        self,
        voice: str = DEFAULT_EDGE_VOICE,
        speed: float = 1.0,
        pitch: int = 0,
        volume: int = 100,
        retries: int = 5,
        retry_delay: float = 1.0,
        fallback_to_gtts: bool = True,
        fallback_to_silent: bool = True,
        language: str = "vi",
    ):
        self.voice = str(voice or "").strip() or DEFAULT_EDGE_VOICE
        self.speed = float(speed)
        self.pitch = int(pitch)
        self.volume = int(volume)
        self.retries = max(0, int(retries))
        self.retry_delay = max(0.0, float(retry_delay))
        self.fallback_to_gtts = fallback_to_gtts
        self.fallback_to_silent = fallback_to_silent
        self.language = language if language in {"vi", "en"} else "vi"
        self.used_voice = self.voice
        self.fallback_message = ""
        self.result_status = "DONE"
        self.actual_output_path: Path | None = None
        self.diagnostics: list[dict[str, Any]] = []
        self.retry_delays = [1, 2, 4, 6, 8]

    @staticmethod
    def speed_to_rate(speed: float) -> str:
        percent = round((max(0.5, min(2.0, speed)) - 1.0) * 100)
        return f"{percent:+d}%"

    @staticmethod
    def pitch_to_string(pitch: int | float) -> str:
        return f"{round(max(-100, min(100, float(pitch)))):+d}Hz"

    @staticmethod
    def volume_to_string(volume: int | float) -> str:
        percent = round(max(0, min(200, float(volume))) - 100)
        return f"{percent:+d}%"

    def _voice_candidates(self) -> list[str]:
        valid = available_voice_ids()
        requested = self.voice if self.voice in valid else DEFAULT_EDGE_VOICE
        candidates = [requested, DEFAULT_EDGE_VOICE, SECONDARY_VI_VOICE]
        result: list[str] = []
        for voice in candidates:
            if voice in valid and voice not in result:
                result.append(voice)
        return result or [DEFAULT_EDGE_VOICE, SECONDARY_VI_VOICE]

    async def _save_chunks(
        self,
        chunks: list[str],
        output_path: Path,
        voice: str,
    ) -> None:
        try:
            import edge_tts
        except ImportError as exc:
            raise RuntimeError(
                "Thiếu edge-tts. Chạy: py -m pip install -r requirements.txt"
            ) from exc

        rate_str = self.speed_to_rate(self.speed)
        pitch_str = self.pitch_to_string(self.pitch)
        volume_str = self.volume_to_string(self.volume)
        with output_path.open("wb") as audio_file:
            for chunk in chunks:
                communicate = edge_tts.Communicate(
                    text=chunk,
                    voice=voice,
                    rate=rate_str,
                    pitch=pitch_str,
                    volume=volume_str,
                )
                received_audio = False
                async for message in communicate.stream():
                    if message["type"] == "audio":
                        received_audio = True
                        audio_file.write(message["data"])
                if not received_audio:
                    raise RuntimeError(
                        f"Edge TTS không trả audio cho chunk: {chunk[:80]}"
                    )

    @staticmethod
    def _prepare_output(target: Path) -> None:
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists():
                target.unlink()
            probe = target.parent / ".tts_write_test.tmp"
            probe.write_bytes(b"ok")
            probe.unlink()
        except PermissionError as exc:
            raise PermissionError(
                f"Không có quyền ghi hoặc file đang bị khóa: {target}"
            ) from exc
        except OSError as exc:
            raise OSError(f"Không thể chuẩn bị output {target}: {exc}") from exc

    def _record_failure(
        self, attempt: int, voice: str, exc: BaseException
    ) -> None:
        self.diagnostics.append(
            {
                "attempt": attempt,
                "voice": voice,
                "exception": f"{type(exc).__name__}: {exc}",
                "traceback": traceback.format_exc(),
            }
        )
        log_exception(
            "app.tts_engines.EdgeTTSEngine.generate",
            exc,
            {
                "attempt": attempt,
                "voice": voice,
                "requested_voice": self.voice,
            },
            trace=self.diagnostics[-1]["traceback"],
        )

    def generate(self, text: str, output_path: str | Path) -> None:
        clean_text = sanitize_tts_text(text)
        if not clean_text:
            raise ValueError("Nội dung rỗng sau khi làm sạch.")
        chunks = split_long_text(clean_text, MAX_EDGE_CHUNK_LENGTH)
        if not chunks:
            raise ValueError("Không tạo được chunk TTS hợp lệ.")

        target = Path(output_path).resolve()
        self._prepare_output(target)
        voices = self._voice_candidates()
        # Một lần gọi đầu tiên và tối đa 5 lần retry.
        total_attempts = max(1, self.retries + 1)
        last_error: BaseException | None = None

        for attempt in range(1, total_attempts + 1):
            voice = voices[min(attempt - 1, len(voices) - 1)]
            try:
                run_async_safely(self._save_chunks(chunks, target, voice))
                if not target.exists() or target.stat().st_size == 0:
                    raise RuntimeError("Edge TTS tạo file rỗng.")
                self.used_voice = voice
                self.actual_output_path = target
                self.result_status = "DONE"
                return
            except BaseException as exc:
                target.unlink(missing_ok=True)
                last_error = exc
                self._record_failure(attempt, voice, exc)
                if attempt < total_attempts:
                    delay_index = min(attempt - 1, len(self.retry_delays) - 1)
                    time.sleep(self.retry_delays[delay_index])

        if self.fallback_to_gtts:
            try:
                fallback = GTTSEngine(self.language, self.speed)
                fallback.generate(clean_text, target)
                self.used_voice = fallback.used_voice
                self.fallback_message = "Edge TTS lỗi, đã fallback sang gTTS"
                self.result_status = "DONE_WITH_FALLBACK"
                self.actual_output_path = target
                return
            except BaseException as exc:
                last_error = exc
                self._record_failure(total_attempts + 1, "gTTS Backup", exc)

        if self.fallback_to_silent:
            try:
                duration_ms = max(1000, min(15000, len(clean_text) * 65))
                silent_path = create_silent_audio(target, duration_ms)
                self.used_voice = "silent"
                self.fallback_message = (
                    "Edge TTS và gTTS đều lỗi, đã tạo silent audio thay thế"
                )
                self.result_status = "SILENT_FALLBACK"
                self.actual_output_path = silent_path
                return
            except BaseException as exc:
                last_error = exc
                self._record_failure(total_attempts + 2, "Silent Fallback", exc)

        raise RuntimeError(
            f"Edge TTS thất bại sau {total_attempts} lần; gTTS và silent fallback "
            f"cũng lỗi. Voice yêu cầu: {self.voice}. Lỗi cuối: {last_error}"
        ) from last_error


class GTTSEngine:
    def __init__(self, language: str = "vi", speed: float = 1.0):
        self.language = language if language in {"vi", "en"} else "vi"
        self.speed = float(speed)
        self.used_voice = f"gTTS-{self.language}"

    def generate(self, text: str, output_path: str | Path) -> None:
        try:
            from gtts import gTTS
        except ImportError as exc:
            raise RuntimeError(
                "Thiếu gTTS. Chạy: py -m pip install -r requirements.txt"
            ) from exc
        clean_text = sanitize_tts_text(text)
        if not clean_text:
            raise ValueError("Nội dung gTTS rỗng sau khi làm sạch.")
        target = Path(output_path).resolve()
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists():
                target.unlink()
            gTTS(
                text=clean_text,
                lang=self.language,
                slow=self.speed < 0.8,
            ).save(str(target))
        except PermissionError as exc:
            target.unlink(missing_ok=True)
            raise PermissionError(f"File đang bị khóa: {target}") from exc
        except Exception:
            target.unlink(missing_ok=True)
            raise
        if not target.exists() or target.stat().st_size == 0:
            target.unlink(missing_ok=True)
            raise RuntimeError("gTTS tạo file rỗng.")


class PiperEngine:
    """Engine Piper chạy offline bằng model ONNX đã import."""

    def __init__(
        self,
        voice_id: str,
        speed: float = 1.0,
        volume: int = 100,
    ):
        self.voice_id = str(voice_id or "").strip()
        self.speed = max(0.5, min(2.0, float(speed)))
        self.volume = max(0, min(200, int(volume)))
        self.used_voice = self.voice_id
        self.result_status = "DONE"
        self.fallback_message = ""
        self.actual_output_path: Path | None = None

    def generate(self, text: str, output_path: str | Path) -> None:
        clean_text = sanitize_tts_text(text)
        if not clean_text:
            raise ValueError("Nội dung Piper rỗng sau khi làm sạch.")
        if not self.voice_id:
            raise ValueError("Chưa chọn Piper voice model.")
        voice_info = get_piper_voice(self.voice_id)
        try:
            from piper import PiperVoice, SynthesisConfig
        except ImportError as exc:
            raise RuntimeError(
                "Thiếu piper-tts. Hãy chạy run.bat hoặc install.bat."
            ) from exc

        target = Path(output_path).resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        wav_target = target.with_suffix(".piper.wav")
        final_wav = target.with_suffix(".wav")
        for old_file in (target, wav_target, final_wav):
            old_file.unlink(missing_ok=True)

        try:
            voice = PiperVoice.load(
                voice_info["model_path"],
                config_path=voice_info["config_path"],
            )
            syn_config = SynthesisConfig(
                length_scale=1.0 / self.speed,
                volume=self.volume / 100.0,
            )
            with wave.open(str(wav_target), "wb") as wav_file:
                voice.synthesize_wav(
                    clean_text,
                    wav_file,
                    syn_config=syn_config,
                )
            if not wav_target.exists() or wav_target.stat().st_size <= 44:
                raise RuntimeError("Piper tạo file WAV rỗng.")

            try:
                from pydub import AudioSegment

                AudioSegment.from_wav(wav_target).export(target, format="mp3")
                wav_target.unlink(missing_ok=True)
                self.actual_output_path = target
            except Exception as convert_error:
                log_exception(
                    "app.tts_engines.PiperEngine.convert_mp3",
                    convert_error,
                    {
                        "voice_id": self.voice_id,
                        "wav_path": wav_target,
                        "mp3_path": target,
                    },
                )
                wav_target.replace(final_wav)
                self.actual_output_path = final_wav
                self.fallback_message = (
                    "Piper tạo WAV thành công nhưng chưa chuyển được sang MP3"
                )

            actual = self.actual_output_path
            if not actual or not actual.exists() or actual.stat().st_size == 0:
                raise RuntimeError("Piper không tạo được audio hợp lệ.")
        except Exception as exc:
            wav_target.unlink(missing_ok=True)
            target.unlink(missing_ok=True)
            log_exception(
                "app.tts_engines.PiperEngine.generate",
                exc,
                {
                    "voice_id": self.voice_id,
                    "model_path": voice_info.get("model_path"),
                    "output_path": target,
                },
            )
            raise


class OpenVoiceCloneEngine:
    """Edge TTS tiếng Việt + OpenVoice đổi màu giọng chạy local trên CPU."""

    RUNTIME_PYTHON = Path(r"D:\AutoTTS_OpenVoice\.venv\Scripts\python.exe")

    def __init__(
        self,
        voice_id: str,
        speed: float = 1.0,
        pitch: int = 0,
        volume: int = 100,
        base_voice: str = DEFAULT_EDGE_VOICE,
    ):
        self.voice_id = str(voice_id or "").strip()
        self.speed = speed
        self.pitch = pitch
        self.volume = volume
        self.base_voice = base_voice or DEFAULT_EDGE_VOICE
        self.used_voice = self.voice_id
        self.result_status = "DONE"
        self.fallback_message = ""
        self.actual_output_path: Path | None = None

    def generate(self, text: str, output_path: str | Path) -> None:
        if not self.RUNTIME_PYTHON.exists():
            raise RuntimeError(
                "Chưa cài OpenVoice runtime. Hãy chạy install_openvoice.bat."
            )
        if not self.voice_id:
            raise ValueError("Chưa chọn voice mẫu WAV/MP3.")
        reference = get_reference_voice(self.voice_id)
        target = Path(output_path).resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        source_path = target.with_suffix(".openvoice_source.mp3")
        clone_wav = target.with_suffix(".openvoice.wav")
        helper = Path(__file__).resolve().parent.parent / "openvoice_worker.py"
        for path in (target, source_path, clone_wav):
            path.unlink(missing_ok=True)

        try:
            source_engine = EdgeTTSEngine(
                voice=self.base_voice,
                speed=self.speed,
                pitch=self.pitch,
                volume=self.volume,
                retries=5,
                fallback_to_gtts=True,
                fallback_to_silent=False,
                language="vi",
            )
            source_engine.generate(text, source_path)
            command = [
                str(self.RUNTIME_PYTHON),
                str(helper),
                "--source",
                str(source_path),
                "--reference",
                reference["audio_path"],
                "--output",
                str(clone_wav),
            ]
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=600,
            )
            if completed.returncode != 0:
                raise RuntimeError(
                    "OpenVoice helper lỗi: "
                    + (completed.stderr.strip() or completed.stdout.strip())
                )
            if not clone_wav.exists() or clone_wav.stat().st_size <= 44:
                raise RuntimeError("OpenVoice tạo file WAV rỗng.")
            try:
                from pydub import AudioSegment

                AudioSegment.from_wav(clone_wav).export(target, format="mp3")
                clone_wav.unlink(missing_ok=True)
                self.actual_output_path = target
            except Exception as convert_error:
                log_exception(
                    "app.tts_engines.OpenVoiceCloneEngine.convert",
                    convert_error,
                    {"clone_wav": clone_wav, "target": target},
                )
                final_wav = target.with_suffix(".wav")
                clone_wav.replace(final_wav)
                self.actual_output_path = final_wav
                self.fallback_message = (
                    "Clone thành công nhưng chưa chuyển được WAV sang MP3"
                )
            source_path.unlink(missing_ok=True)
            actual = self.actual_output_path
            if not actual or not actual.exists() or actual.stat().st_size == 0:
                raise RuntimeError("OpenVoice không tạo được audio hợp lệ.")
        except Exception as exc:
            log_exception(
                "app.tts_engines.OpenVoiceCloneEngine.generate",
                exc,
                {
                    "voice_id": self.voice_id,
                    "reference": reference.get("audio_path"),
                    "output": target,
                },
            )
            source_path.unlink(missing_ok=True)
            clone_wav.unlink(missing_ok=True)
            target.unlink(missing_ok=True)
            raise


class XTTSCloneEngine:
    """XTTS-v2 local clone engine for supported languages only."""

    RUNTIME_PYTHON = Path(r"D:\AutoTTS_XTTS\.venv\Scripts\python.exe")
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

    def __init__(
        self,
        voice_id: str,
        language: str = "en",
        speed: float = 1.0,
    ):
        self.voice_id = str(voice_id or "").strip()
        self.language = str(language or "en").strip().lower()
        self.speed = max(0.75, min(1.25, float(speed)))
        self.used_voice = self.voice_id
        self.result_status = "DONE"
        self.fallback_message = ""
        self.actual_output_path: Path | None = None

    def generate(self, text: str, output_path: str | Path) -> None:
        if not self.RUNTIME_PYTHON.exists():
            raise RuntimeError(
                "ChÆ°a cÃ i XTTS runtime. HÃ£y cháº¡y install_xtts.bat."
            )
        if not self.voice_id:
            raise ValueError("ChÆ°a chá»n voice máº«u cho XTTS.")

        clean_text = sanitize_tts_text(text)
        if not clean_text:
            raise ValueError("Ná»™i dung XTTS rá»—ng sau khi lÃ m sáº¡ch.")
        if self.language == "vi":
            raise ValueError(
                "XTTS Local hiá»‡n chÆ°a há»— trá»£ tiáº¿ng Viá»‡t á»Ÿ báº£n tÃ­ch há»£p nÃ y. "
                "HÃ£y dÃ¹ng Local Voice Clone cho tiáº¿ng Viá»‡t."
            )
        if self.language not in self.SUPPORTED_LANGUAGES:
            supported = ", ".join(sorted(self.SUPPORTED_LANGUAGES))
            raise ValueError(
                f"XTTS khÃ´ng há»— trá»£ language '{self.language}'. "
                f"NgÃ´n ngá»¯ há»£p lá»‡: {supported}"
            )

        reference = get_reference_voice(self.voice_id)
        reference_files = get_reference_audio_files(self.voice_id)
        if not reference_files:
            raise RuntimeError("KhÃ´ng tÃ¬m tháº¥y reference audio cho XTTS.")

        target = Path(output_path).resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        helper = Path(__file__).resolve().parent.parent / "xtts_worker.py"
        target.unlink(missing_ok=True)

        command = [
            str(self.RUNTIME_PYTHON),
            str(helper),
            "--text",
            clean_text,
            "--language",
            self.language,
            "--output",
            str(target),
            "--speed",
            f"{self.speed:.2f}",
        ]
        for audio_path in reference_files:
            command.extend(["--speaker-wav", audio_path])

        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=1800,
            )
            if completed.returncode != 0:
                raise RuntimeError(
                    "XTTS helper lá»—i: "
                    + (completed.stderr.strip() or completed.stdout.strip())
                )
            if not target.exists() or target.stat().st_size == 0:
                raise RuntimeError("XTTS khÃ´ng táº¡o Ä‘Æ°á»£c audio há»£p lá»‡.")
            self.actual_output_path = target
            self.used_voice = reference.get("name", self.voice_id)
        except Exception as exc:
            log_exception(
                "app.tts_engines.XTTSCloneEngine.generate",
                exc,
                {
                    "voice_id": self.voice_id,
                    "reference_files": reference_files,
                    "language": self.language,
                    "output": target,
                },
            )
            target.unlink(missing_ok=True)
            raise
