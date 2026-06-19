import re
from pathlib import Path

from .utils import split_long_text


def _content_to_string(value: object) -> str:
    """Đảm bảo content luôn là chuỗi sạch, không phải None hoặc list."""
    if value is None:
        return ""
    if isinstance(value, (list, tuple, set)):
        value = " ".join(str(item) for item in value if item is not None)
    return re.sub(r"\s+", " ", str(value)).strip()


def _read_text(path: str | Path, encodings: tuple[str, ...]) -> str:
    raw = Path(path).read_bytes()
    for encoding in encodings:
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode(encodings[-1], errors="replace")


def parse_srt(path: str | Path) -> list[dict]:
    text = _read_text(path, ("utf-8-sig", "cp1258", "latin-1"))
    text = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    blocks = re.split(r"\n{2,}", text)
    segments: list[dict] = []
    timing_pattern = re.compile(
        r"(\d{1,2}:\d{2}:\d{2}[,.]\d{3})\s*-->\s*"
        r"(\d{1,2}:\d{2}:\d{2}[,.]\d{3})"
    )
    for block in blocks:
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        timing_index = next(
            (i for i, line in enumerate(lines) if timing_pattern.search(line)), None
        )
        if timing_index is None:
            continue
        match = timing_pattern.search(lines[timing_index])
        if not match:
            continue
        content = _content_to_string(lines[timing_index + 1 :])
        if not content:
            continue
        segments.append(
            {
                "timing": f"{match.group(1).replace('.', ',')} --> "
                f"{match.group(2).replace('.', ',')}",
                "content": content,
            }
        )
    return segments


def parse_txt(path: str | Path) -> list[dict]:
    text = _read_text(path, ("utf-8-sig", "cp1258", "latin-1"))
    segments: list[dict] = []
    for line in text.splitlines():
        clean_line = _content_to_string(line)
        for chunk in split_long_text(clean_line, 350):
            segments.append({"timing": "", "content": _content_to_string(chunk)})
    return segments


def parse_dat(path: str | Path) -> list[dict]:
    return parse_txt(path)


def parse_file(path: str | Path) -> list[dict]:
    suffix = Path(path).suffix.lower()
    if suffix == ".srt":
        return parse_srt(path)
    if suffix == ".txt":
        return parse_txt(path)
    if suffix == ".dat":
        return parse_dat(path)
    raise ValueError(f"Định dạng không được hỗ trợ: {suffix}")
