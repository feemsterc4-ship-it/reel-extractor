"""Speech-to-text via faster-whisper (local, free)."""
from __future__ import annotations

import os
import threading
from typing import Optional

_model = None
_model_lock = threading.Lock()

MODEL_SIZE = os.environ.get("WHISPER_MODEL", "base")
# int8 keeps memory low and is fast on CPU-only hosts.
COMPUTE_TYPE = os.environ.get("WHISPER_COMPUTE_TYPE", "int8")
DEVICE = os.environ.get("WHISPER_DEVICE", "cpu")


def get_model():
    """Lazily load the Whisper model once per process."""
    global _model
    if _model is None:
        with _model_lock:
            if _model is None:
                from faster_whisper import WhisperModel

                _model = WhisperModel(MODEL_SIZE, device=DEVICE, compute_type=COMPUTE_TYPE)
    return _model


def transcribe(video_path: str, language: Optional[str] = None) -> dict:
    """Transcribe the audio track of a video file.

    Returns {"text", "segments", "language"}.
    """
    model = get_model()
    segments_iter, info = model.transcribe(
        video_path,
        language=language,
        vad_filter=True,  # skip silence/music-only stretches
        beam_size=5,
    )
    segments = []
    parts = []
    for seg in segments_iter:
        text = seg.text.strip()
        if not text:
            continue
        segments.append({"start": round(seg.start, 2), "end": round(seg.end, 2), "text": text})
        parts.append(text)
    return {
        "text": " ".join(parts) or None,
        "segments": segments,
        "language": getattr(info, "language", None),
    }
