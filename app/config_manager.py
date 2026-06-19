import json
import sys
from pathlib import Path
from typing import Any


DEFAULT_CONFIG = {
    "default_engine": "edge",
    "default_voice": "vi-VN-HoaiMyNeural",
    "default_piper_voice": "",
    "default_clone_voice": "",
    "default_xtts_voice": "",
    "output_dir": r"D:\AutoTTS_Output",
    "speed": 1.0,
    "pitch": 0,
    "volume": 100,
    "language": "Auto",
}


def resolve_output_dir(configured: str | Path | None = None) -> Path:
    """Ưu tiên ổ D; fallback ./output nếu ổ D không tồn tại hoặc không ghi được."""
    requested = Path(configured or DEFAULT_CONFIG["output_dir"])
    local_fallback = app_dir() / "output"
    candidates = [requested, local_fallback]
    for candidate in candidates:
        try:
            if candidate.drive and not Path(candidate.drive + "\\").exists():
                continue
            candidate.mkdir(parents=True, exist_ok=True)
            probe = candidate / ".output_write_test.tmp"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink()
            return candidate.resolve()
        except OSError:
            continue
    return local_fallback.resolve()


def app_dir() -> Path:
    """Trả về thư mục chứa ứng dụng, kể cả khi chạy từ file EXE."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def config_path() -> Path:
    return app_dir() / "config.json"


def load_config(path: Path | None = None) -> dict[str, Any]:
    target = path or config_path()
    config = DEFAULT_CONFIG.copy()
    try:
        if target.exists():
            loaded = json.loads(target.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                # Chỉ nhận các khóa cấu hình đang được ứng dụng sử dụng.
                config.update(
                    {key: loaded[key] for key in DEFAULT_CONFIG if key in loaded}
                )
    except (OSError, json.JSONDecodeError):
        return config
    return config


def save_config(config: dict[str, Any], path: Path | None = None) -> None:
    target = path or config_path()
    clean_config = {
        key: config.get(key, value) for key, value in DEFAULT_CONFIG.items()
    }
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(clean_config, ensure_ascii=False, indent=2), encoding="utf-8"
    )
