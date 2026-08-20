"""OCR of on-screen text: sample frames with ffmpeg, read them with Tesseract."""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from difflib import SequenceMatcher

# One frame every N seconds is plenty for reels-style text overlays.
FRAME_INTERVAL = float(os.environ.get("OCR_FRAME_INTERVAL", "1.5"))
MAX_FRAMES = int(os.environ.get("OCR_MAX_FRAMES", "80"))
OCR_LANGS = os.environ.get("OCR_LANGS", "eng")

_WORD_RE = re.compile(r"[A-Za-zÀ-￿]{2,}")


def _clean_line(line: str) -> str:
    return " ".join(line.split()).strip()


def _looks_like_text(line: str) -> bool:
    """Filter OCR noise: keep lines with at least one real word."""
    return bool(_WORD_RE.search(line)) and len(line) >= 3


def _similar(a: str, b: str, threshold: float = 0.82) -> bool:
    return SequenceMatcher(None, a.lower(), b.lower()).ratio() >= threshold


def _dedupe(lines: list[str]) -> list[str]:
    """Drop near-duplicate lines (same overlay OCR'd from many frames)."""
    kept: list[str] = []
    for line in lines:
        if any(_similar(line, existing) for existing in kept):
            continue
        kept.append(line)
    return kept


def ocr_video(video_path: str) -> list[str]:
    """Return deduplicated on-screen text lines found in the video."""
    if not shutil.which("ffmpeg") or not shutil.which("tesseract"):
        raise RuntimeError("ffmpeg and tesseract must be installed for OCR.")

    import pytesseract
    from PIL import Image

    framedir = tempfile.mkdtemp(prefix="reel_frames_")
    try:
        subprocess.run(
            [
                "ffmpeg", "-hide_banner", "-loglevel", "error",
                "-i", video_path,
                "-vf", f"fps=1/{FRAME_INTERVAL},scale=720:-1",
                "-frames:v", str(MAX_FRAMES),
                os.path.join(framedir, "frame_%04d.png"),
            ],
            check=True,
            timeout=120,
        )
        lines: list[str] = []
        for name in sorted(os.listdir(framedir)):
            path = os.path.join(framedir, name)
            with Image.open(path) as img:
                raw = pytesseract.image_to_string(img, lang=OCR_LANGS)
            for line in raw.splitlines():
                line = _clean_line(line)
                if _looks_like_text(line):
                    lines.append(line)
        return _dedupe(lines)
    finally:
        shutil.rmtree(framedir, ignore_errors=True)
