import os
import re
import subprocess
from pathlib import Path


def sanitize_filename(name: str, fallback: str = "audio") -> str:
    """Loại ký tự không hợp lệ trong tên file Windows."""
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip(" .")
    return cleaned[:180] or fallback


def split_long_text(text: str, max_length: int = 350) -> list[str]:
    """Chia văn bản dài theo câu, sau đó theo từ nếu câu vẫn quá dài."""
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return []
    if len(text) <= max_length:
        return [text]

    sentences = re.split(r"(?<=[.!?…;:])\s+", text)
    chunks: list[str] = []
    current = ""
    for sentence in sentences:
        if len(sentence) > max_length:
            words = sentence.split()
            for word in words:
                candidate = f"{current} {word}".strip()
                if len(candidate) <= max_length:
                    current = candidate
                else:
                    if current:
                        chunks.append(current)
                    current = word
            continue
        candidate = f"{current} {sentence}".strip()
        if len(candidate) <= max_length:
            current = candidate
        else:
            if current:
                chunks.append(current)
            current = sentence
    if current:
        chunks.append(current)
    return chunks


def open_folder(path: str | Path) -> None:
    target = Path(path).resolve()
    target.mkdir(parents=True, exist_ok=True)
    if os.name == "nt":
        os.startfile(str(target))  # type: ignore[attr-defined]
    elif os.name == "posix":
        command = "open" if subprocess.run(
            ["uname"], capture_output=True, text=True
        ).stdout.strip() == "Darwin" else "xdg-open"
        subprocess.Popen([command, str(target)])
    else:
        raise OSError("Hệ điều hành không hỗ trợ mở thư mục tự động.")
