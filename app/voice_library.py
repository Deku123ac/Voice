import json
import shutil
from pathlib import Path

from .config_manager import app_dir
from .error_logger import log_exception
from .utils import sanitize_filename


LIBRARY_DIR = app_dir() / "voices" / "references"
REGISTRY_PATH = LIBRARY_DIR / "voices.json"
SUPPORTED_AUDIO = {".wav", ".mp3", ".m4a", ".flac", ".ogg"}
TARGET_SAMPLE_RATE = 22050
MIN_REFERENCE_MS = 6000
MAX_REFERENCE_MS = 25000


def _load() -> list[dict[str, str]]:
    try:
        data = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)]
    except (OSError, json.JSONDecodeError):
        return []
    return []


def _save(voices: list[dict[str, str]]) -> None:
    LIBRARY_DIR.mkdir(parents=True, exist_ok=True)
    REGISTRY_PATH.write_text(
        json.dumps(voices, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _upgrade_entry(entry: dict[str, str]) -> dict[str, str]:
    source_audio = Path(
        str(
            entry.get("source_audio_path")
            or entry.get("audio_path")
            or ""
        )
    )
    if not source_audio.is_file():
        return entry

    audio_path = Path(str(entry.get("audio_path") or ""))
    needs_prepare = (
        not audio_path.is_file()
        or audio_path.suffix.lower() != ".wav"
        or not entry.get("duration_ms")
    )
    if not needs_prepare:
        return entry

    prepared_target = source_audio.parent / "reference.wav"
    try:
        prepared = _prepare_reference_audio(source_audio, prepared_target)
    except Exception as exc:
        log_exception(
            "app.voice_library._upgrade_entry",
            exc,
            {"source_audio": source_audio, "entry": entry},
        )
        return entry

    upgraded = dict(entry)
    upgraded["audio_path"] = str(prepared_target.resolve())
    upgraded["source_audio_path"] = str(source_audio.resolve())
    upgraded["duration_ms"] = int(prepared["duration_ms"])
    upgraded["original_duration_ms"] = int(prepared["original_duration_ms"])
    upgraded["sample_rate"] = int(prepared["sample_rate"])
    upgraded["quality_note"] = str(prepared.get("note", ""))
    return upgraded


def _prepare_reference_audio(source: Path, target: Path) -> dict[str, str | int | float]:
    try:
        from pydub import AudioSegment, effects
        from pydub.silence import detect_nonsilent
    except ImportError as exc:
        raise RuntimeError(
            "Thiếu pydub nên chưa thể làm sạch voice mẫu. Hãy chạy run.bat."
        ) from exc

    audio = AudioSegment.from_file(source)
    original_duration_ms = len(audio)
    audio = audio.set_channels(1).set_frame_rate(TARGET_SAMPLE_RATE)
    if audio.sample_width != 2:
        audio = audio.set_sample_width(2)

    cleaned = audio.high_pass_filter(80).low_pass_filter(7500)
    silence_threshold = max(-42, int(cleaned.dBFS - 18)) if cleaned.dBFS != float("-inf") else -42
    ranges = detect_nonsilent(
        cleaned,
        min_silence_len=250,
        silence_thresh=silence_threshold,
        seek_step=10,
    )

    if ranges:
        combined = AudioSegment.silent(duration=0, frame_rate=TARGET_SAMPLE_RATE)
        retained_ms = 0
        for start, end in ranges:
            clip = cleaned[max(0, start - 80) : min(len(cleaned), end + 120)]
            if len(clip) < 350:
                continue
            if retained_ms and retained_ms < MAX_REFERENCE_MS:
                combined += AudioSegment.silent(duration=100, frame_rate=TARGET_SAMPLE_RATE)
            remaining = MAX_REFERENCE_MS - retained_ms
            if remaining <= 0:
                break
            if len(clip) > remaining:
                clip = clip[:remaining]
            combined += clip
            retained_ms += len(clip)
            if retained_ms >= MAX_REFERENCE_MS:
                break
        if len(combined) >= 1000:
            cleaned = combined
    else:
        cleaned = cleaned[:MAX_REFERENCE_MS]

    if len(cleaned) > MAX_REFERENCE_MS:
        cleaned = cleaned[:MAX_REFERENCE_MS]
    if len(cleaned) == 0:
        raise ValueError("Voice mẫu không có đoạn nói hợp lệ sau khi làm sạch.")

    cleaned = effects.normalize(cleaned, headroom=2.0).fade_in(20).fade_out(80)
    target.parent.mkdir(parents=True, exist_ok=True)
    cleaned.export(target, format="wav")

    notes: list[str] = []
    if original_duration_ms < MIN_REFERENCE_MS:
        notes.append("file mẫu hơi ngắn, nên ghi ít nhất 10 giây")
    if len(cleaned) < MIN_REFERENCE_MS:
        notes.append("đoạn nói sau làm sạch hơi ngắn, độ giống có thể giảm")
    if original_duration_ms > 45000:
        notes.append("file gốc dài, app chỉ giữ phần nói rõ nhất khoảng 25 giây")
    if not ranges:
        notes.append("không tách được khoảng lặng rõ ràng, nên ghi ở nơi yên tĩnh hơn")

    return {
        "duration_ms": len(cleaned),
        "original_duration_ms": original_duration_ms,
        "sample_rate": TARGET_SAMPLE_RATE,
        "note": "; ".join(notes),
    }


def list_reference_voices() -> list[dict[str, str]]:
    original = _load()
    voices = [_upgrade_entry(voice) for voice in original if isinstance(voice, dict)]
    voices = [
        voice
        for voice in voices
        if Path(str(voice.get("audio_path", ""))).is_file()
    ]
    if voices != original:
        _save(voices)
    return voices


def get_reference_voice(voice_id: str) -> dict[str, str]:
    for voice in list_reference_voices():
        if voice["id"] == voice_id:
            return voice
    raise KeyError(f"Không tìm thấy voice mẫu: {voice_id}")


def get_reference_audio_files(voice_id: str) -> list[str]:
    voice = get_reference_voice(voice_id)
    voice_dir = Path(str(voice.get("audio_path", ""))).parent
    candidates: list[Path] = []
    if voice_dir.is_dir():
        for item in sorted(voice_dir.iterdir()):
            if item.is_file() and item.suffix.lower() in SUPPORTED_AUDIO:
                candidates.append(item)
    if not candidates and voice.get("audio_path"):
        candidates.append(Path(str(voice["audio_path"])))
    files: list[str] = []
    seen: set[str] = set()
    for path in candidates:
        resolved = str(path.resolve())
        if resolved not in seen:
            seen.add(resolved)
            files.append(resolved)
    return files


def import_reference_voice(
    audio_file: str | Path,
    display_name: str,
) -> dict[str, str]:
    source = Path(audio_file).resolve()
    if not source.is_file() or source.suffix.lower() not in SUPPORTED_AUDIO:
        raise ValueError("Chỉ hỗ trợ WAV, MP3, M4A, FLAC hoặc OGG.")
    voice_id = sanitize_filename(display_name or source.stem, "reference_voice")
    voice_dir = LIBRARY_DIR / voice_id
    voice_dir.mkdir(parents=True, exist_ok=True)
    original_target = voice_dir / f"source{source.suffix.lower()}"
    prepared_target = voice_dir / "reference.wav"
    shutil.copy2(source, original_target)
    try:
        prepared = _prepare_reference_audio(original_target, prepared_target)
    except Exception as exc:
        log_exception(
            "app.voice_library.import_reference_voice.prepare",
            exc,
            {"source": source, "target": prepared_target},
        )
        raise
    entry = {
        "id": voice_id,
        "name": display_name.strip() or source.stem,
        "audio_path": str(prepared_target.resolve()),
        "source_audio_path": str(original_target.resolve()),
        "duration_ms": int(prepared["duration_ms"]),
        "original_duration_ms": int(prepared["original_duration_ms"]),
        "sample_rate": int(prepared["sample_rate"]),
        "quality_note": str(prepared.get("note", "")),
    }
    voices = [voice for voice in _load() if voice.get("id") != voice_id]
    voices.append(entry)
    voices.sort(key=lambda voice: voice["name"].lower())
    _save(voices)
    return entry


def remove_reference_voice(voice_id: str) -> None:
    voices = _load()
    selected = next((voice for voice in voices if voice.get("id") == voice_id), None)
    if selected:
        folder = Path(selected["audio_path"]).parent
        if LIBRARY_DIR in folder.parents:
            shutil.rmtree(folder, ignore_errors=True)
    _save([voice for voice in voices if voice.get("id") != voice_id])
