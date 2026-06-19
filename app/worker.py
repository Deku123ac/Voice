import threading
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, Signal, Slot

from .audio_utils import (
    MissingAudioDependencyError,
    create_silent_audio,
    join_mp3_files,
)
from .error_logger import log_exception
from .tts_engines import (
    DEFAULT_EDGE_VOICE,
    EdgeTTSEngine,
    GTTSEngine,
    OpenVoiceCloneEngine,
    PiperEngine,
    XTTSCloneEngine,
    sanitize_tts_text,
)


class BatchTTSWorker(QObject):
    row_status = Signal(int, str, str, str)
    log = Signal(str)
    finished = Signal(bool, str)

    def __init__(
        self,
        segments: list[dict[str, Any]],
        output_dir: str,
        options: dict[str, Any],
    ):
        super().__init__()
        self.segments = segments
        self.output_dir = Path(output_dir).resolve()
        self.options = options
        self._stop_event = threading.Event()
        self.error_log = Path(__file__).resolve().parent.parent / "logs" / "error.log"

    def request_stop(self) -> None:
        self._stop_event.set()

    def _engine(self, voice: str):
        engine = self.options.get("engine", "edge")
        if engine == "edge":
            return EdgeTTSEngine(
                voice=voice or DEFAULT_EDGE_VOICE,
                speed=float(self.options.get("speed", 1.0)),
                pitch=int(self.options.get("pitch", 0)),
                volume=int(self.options.get("volume", 100)),
                retries=5,
                retry_delay=1.0,
                fallback_to_gtts=True,
                language=self.options.get("language_code", "vi"),
            )
        if engine == "gtts":
            return GTTSEngine(
                self.options.get("language_code", "vi"),
                float(self.options.get("speed", 1.0)),
            )
        if engine == "openvoice":
            return OpenVoiceCloneEngine(
                voice_id=voice,
                speed=float(self.options.get("speed", 1.0)),
                pitch=int(self.options.get("pitch", 0)),
                volume=int(self.options.get("volume", 100)),
                base_voice=DEFAULT_EDGE_VOICE,
            )
        if engine == "xtts":
            return XTTSCloneEngine(
                voice_id=voice,
                language=str(self.options.get("language_code", "en")),
                speed=float(self.options.get("speed", 1.0)),
            )
        return PiperEngine(
            voice_id=voice,
            speed=float(self.options.get("speed", 1.0)),
            volume=int(self.options.get("volume", 100)),
        )

    def _prepare_output_dir(self) -> None:
        try:
            self.output_dir.mkdir(parents=True, exist_ok=True)
            probe = self.output_dir / ".write_test.tmp"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink()
        except PermissionError as exc:
            raise PermissionError(
                f"Không có quyền ghi vào thư mục output: {self.output_dir}"
            ) from exc
        except OSError as exc:
            raise OSError(
                f"Không thể tạo hoặc ghi vào thư mục output {self.output_dir}: {exc}"
            ) from exc

    def _write_error_log(self, detail: str, trace: str) -> None:
        try:
            self.error_log.parent.mkdir(parents=True, exist_ok=True)
            with self.error_log.open("a", encoding="utf-8") as log_file:
                log_file.write("\n" + "=" * 90 + "\n")
                log_file.write(
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S") + "\n"
                )
                log_file.write(detail + "\n\nTRACEBACK:\n" + trace + "\n")
        except OSError as log_error:
            self.log.emit(f"Không thể ghi logs/error.log: {log_error}")

    @Slot()
    def run(self) -> None:
        had_error = False
        try:
            self._prepare_output_dir()
            for row, raw_segment in enumerate(self.segments):
                if self._stop_event.is_set():
                    self.log.emit(
                        "Đã nhận yêu cầu dừng. Các dòng còn lại giữ WAITING."
                    )
                    self.finished.emit(False, "Đã dừng an toàn.")
                    return

                segment = raw_segment if isinstance(raw_segment, dict) else {}
                segment_id = str(segment.get("id") or row + 1)
                text = sanitize_tts_text(segment.get("content"))
                status = str(segment.get("status") or "WAITING")
                engine_name = str(self.options.get("engine") or "edge")
                voice = sanitize_tts_text(
                    segment.get("voice") or self.options.get("voice")
                )
                if engine_name == "edge" and not voice:
                    voice = DEFAULT_EDGE_VOICE
                target = self.output_dir / f"{row + 1:03d}.mp3"

                if not text:
                    reason = "Nội dung rỗng sau khi làm sạch."
                    self.row_status.emit(row, "SKIPPED", "", reason)
                    self.log.emit(f"Segment {segment_id} SKIPPED: {reason}")
                    continue
                if (
                    self.options.get("skip_done")
                    and status in {"DONE", "DONE_WITH_FALLBACK", "SILENT_FALLBACK"}
                    and target.exists()
                ):
                    self.row_status.emit(row, "DONE", target.name, "")
                    self.log.emit(f"Bỏ qua segment {segment_id}: đã hoàn thành.")
                    continue

                self.row_status.emit(row, "PROCESSING", target.name, "")
                self.log.emit(
                    f"Đang xử lý segment {segment_id} | engine={engine_name} | "
                    f"voice={voice or '(mặc định)'} | output={target}"
                )
                try:
                    engine = self._engine(voice)
                    engine.generate(text, target)
                    used_voice = getattr(engine, "used_voice", voice)
                    fallback_message = getattr(engine, "fallback_message", "")
                    result_status = getattr(engine, "result_status", "DONE")
                    actual_output = getattr(engine, "actual_output_path", target)
                    diagnostics = getattr(engine, "diagnostics", [])
                    for diagnostic in diagnostics:
                        attempt_detail = (
                            f"EDGE ATTEMPT ERROR\n"
                            f"segment ID: {segment_id}\n"
                            f"content: {text}\n"
                            f"voice: {diagnostic.get('voice', voice)}\n"
                            f"engine: {engine_name}\n"
                            f"output_path: {target}\n"
                            f"attempt number: {diagnostic.get('attempt')}\n"
                            f"full exception: {diagnostic.get('exception')}"
                        )
                        attempt_trace = str(diagnostic.get("traceback", ""))
                        self.log.emit(attempt_detail)
                        self.log.emit("TRACEBACK:\n" + attempt_trace)
                        self._write_error_log(attempt_detail, attempt_trace)
                    self.row_status.emit(
                        row,
                        result_status,
                        Path(actual_output).name,
                        fallback_message,
                    )
                    self.log.emit(
                        f"Hoàn thành segment {segment_id}: {target.name} "
                        f"(voice={used_voice})"
                    )
                    if fallback_message:
                        self.log.emit(
                            f"Segment {segment_id}: {fallback_message}"
                        )
                except Exception as exc:
                    trace = traceback.format_exc()
                    error_message = f"{type(exc).__name__}: {exc}"
                    detail = (
                        f"SEGMENT TTS ERROR\n"
                        f"segment ID: {segment_id}\n"
                        f"text: {text}\n"
                        f"voice: {voice or '(trống)'}\n"
                        f"engine: {engine_name}\n"
                        f"output: {target}\n"
                        f"attempt number: xem diagnostics phía trên\n"
                        f"exception: {error_message}"
                    )
                    self.log.emit(detail)
                    self.log.emit("TRACEBACK:\n" + trace)
                    self._write_error_log(detail, trace)
                    log_exception(
                        "app.worker.BatchTTSWorker.run.segment",
                        exc,
                        {
                            "segment_id": segment_id,
                            "content": text,
                            "voice": voice,
                            "engine": engine_name,
                            "output_path": target,
                        },
                        trace=trace,
                    )
                    try:
                        duration_ms = max(1000, min(15000, len(text) * 65))
                        silent_path = create_silent_audio(target, duration_ms)
                        fallback_message = (
                            "TTS lỗi, đã tạo silent audio thay thế"
                        )
                        self.row_status.emit(
                            row,
                            "SILENT_FALLBACK",
                            silent_path.name,
                            fallback_message,
                        )
                        self.log.emit(
                            f"Segment {segment_id}: {fallback_message}"
                        )
                    except Exception as silent_error:
                        had_error = True
                        silent_trace = traceback.format_exc()
                        combined_error = (
                            f"{error_message}; silent fallback lỗi: "
                            f"{type(silent_error).__name__}: {silent_error}"
                        )
                        self.row_status.emit(
                            row, "ERROR", target.name, combined_error
                        )
                        log_exception(
                            "app.worker.BatchTTSWorker.run.silent_fallback",
                            silent_error,
                            {
                                "segment_id": segment_id,
                                "output_path": target,
                            },
                            trace=silent_trace,
                        )

            if self.options.get("create_srt"):
                self._write_srt()
                self.log.emit("Đã tạo generated_subtitles.srt.")

            if self.options.get("auto_join") and not had_error:
                try:
                    joined = join_mp3_files(self.output_dir)
                    self.log.emit(f"Đã nối MP3: {joined.name}")
                except MissingAudioDependencyError as exc:
                    self.log.emit(str(exc))
                    log_exception(
                        "app.worker.BatchTTSWorker.run.auto_join",
                        exc,
                        {"output_dir": self.output_dir},
                    )
                except Exception as exc:
                    self.log.emit(f"Không thể tự động nối MP3: {exc}")
                    log_exception(
                        "app.worker.BatchTTSWorker.run.auto_join",
                        exc,
                        {"output_dir": self.output_dir},
                    )

            message = (
                "Đã chạy xong, có segment lỗi. Xem cột Error và logs/error.log."
                if had_error
                else "Đã hoàn thành toàn bộ batch."
            )
            self.finished.emit(not had_error, message)
        except Exception as exc:
            trace = traceback.format_exc()
            detail = (
                f"BATCH ERROR\n"
                f"engine: {self.options.get('engine', 'edge')}\n"
                f"output: {self.output_dir}\n"
                f"exception: {type(exc).__name__}: {exc}"
            )
            self.log.emit(detail)
            self.log.emit("TRACEBACK:\n" + trace)
            self._write_error_log(detail, trace)
            log_exception(
                "app.worker.BatchTTSWorker.run.batch",
                exc,
                {
                    "engine": self.options.get("engine", "edge"),
                    "output_dir": self.output_dir,
                },
                trace=trace,
            )
            self.finished.emit(False, str(exc))

    def _write_srt(self) -> None:
        lines: list[str] = []
        cursor_ms = 0
        for index, segment in enumerate(self.segments, 1):
            safe_segment = segment if isinstance(segment, dict) else {}
            content = sanitize_tts_text(safe_segment.get("content"))
            timing = sanitize_tts_text(safe_segment.get("timing"))
            if not timing:
                duration = max(1500, min(12000, len(content) * 65))
                timing = (
                    f"{self._format_ms(cursor_ms)} --> "
                    f"{self._format_ms(cursor_ms + duration)}"
                )
                cursor_ms += duration
            lines.extend([str(index), timing, content, ""])
        (self.output_dir / "generated_subtitles.srt").write_text(
            "\n".join(lines), encoding="utf-8"
        )

    @staticmethod
    def _format_ms(value: int) -> str:
        hours, remainder = divmod(value, 3_600_000)
        minutes, remainder = divmod(remainder, 60_000)
        seconds, milliseconds = divmod(remainder, 1000)
        return f"{hours:02d}:{minutes:02d}:{seconds:02d},{milliseconds:03d}"
