import json
import shutil
from pathlib import Path
from typing import Any

from .config_manager import app_dir
from .utils import sanitize_filename


PIPER_VOICES_DIR = app_dir() / "voices" / "piper"
PIPER_REGISTRY = PIPER_VOICES_DIR / "voices.json"


def _load_registry() -> list[dict[str, Any]]:
    try:
        data = json.loads(PIPER_REGISTRY.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)]
    except (OSError, json.JSONDecodeError):
        return []
    return []


def _save_registry(voices: list[dict[str, Any]]) -> None:
    PIPER_VOICES_DIR.mkdir(parents=True, exist_ok=True)
    PIPER_REGISTRY.write_text(
        json.dumps(voices, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _find_config(model_path: Path) -> Path:
    candidates = [
        Path(str(model_path) + ".json"),
        model_path.with_suffix(".json"),
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise FileNotFoundError(
        "Không tìm thấy file cấu hình Piper. Cần đặt cạnh model một trong hai "
        f"file: {model_path.name}.json hoặc {model_path.stem}.json"
    )


def list_piper_voices() -> list[dict[str, str]]:
    voices: list[dict[str, str]] = []
    changed = False
    for item in _load_registry():
        model_path = Path(str(item.get("model_path", "")))
        config_path = Path(str(item.get("config_path", "")))
        if model_path.exists() and config_path.exists():
            voices.append(
                {
                    "id": str(item.get("id", model_path.stem)),
                    "name": str(item.get("name", model_path.stem)),
                    "model_path": str(model_path),
                    "config_path": str(config_path),
                }
            )
        else:
            changed = True
    if changed:
        _save_registry(voices)
    return voices


def get_piper_voice(voice_id: str) -> dict[str, str]:
    for voice in list_piper_voices():
        if voice["id"] == voice_id:
            return voice
    raise KeyError(
        f"Không tìm thấy Piper voice '{voice_id}'. Hãy Import Piper Model trước."
    )


def import_piper_voice(
    model_file: str | Path,
    display_name: str | None = None,
) -> dict[str, str]:
    source_model = Path(model_file).resolve()
    if source_model.suffix.lower() != ".onnx" or not source_model.is_file():
        raise ValueError("Piper model phải là file .onnx hợp lệ.")
    source_config = _find_config(source_model)

    voice_id = sanitize_filename(source_model.stem, "piper_voice")
    voice_dir = PIPER_VOICES_DIR / voice_id
    voice_dir.mkdir(parents=True, exist_ok=True)
    target_model = voice_dir / source_model.name
    target_config = voice_dir / f"{source_model.name}.json"
    shutil.copy2(source_model, target_model)
    shutil.copy2(source_config, target_config)

    entry = {
        "id": voice_id,
        "name": (display_name or source_model.stem).strip() or source_model.stem,
        "model_path": str(target_model.resolve()),
        "config_path": str(target_config.resolve()),
    }
    voices = [voice for voice in _load_registry() if voice.get("id") != voice_id]
    voices.append(entry)
    voices.sort(key=lambda voice: str(voice.get("name", "")).lower())
    _save_registry(voices)
    return entry


def remove_piper_voice(voice_id: str) -> None:
    voices = _load_registry()
    selected = next((item for item in voices if item.get("id") == voice_id), None)
    if selected:
        voice_dir = Path(str(selected.get("model_path", ""))).parent
        if voice_dir.is_dir() and PIPER_VOICES_DIR in voice_dir.parents:
            shutil.rmtree(voice_dir, ignore_errors=True)
    _save_registry([item for item in voices if item.get("id") != voice_id])
