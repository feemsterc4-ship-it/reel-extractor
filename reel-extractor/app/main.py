"""Reel Extractor API — turn an Instagram reel link into structured knowledge.

Designed to be plugged into a ChatGPT Custom GPT as an Action (or called from
any client). Given a reel URL it returns the caption, hashtags, author,
engagement stats, a spoken-word transcript (faster-whisper, local/free), and
the text overlays shown on screen (OCR).
"""
from __future__ import annotations

import logging
import os
import shutil
import time
from collections import OrderedDict
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Security
from fastapi.security.api_key import APIKeyHeader

from .extractor import InvalidUrlError, build_metadata, fetch_reel, parse_shortcode
from .models import ExtractRequest, ExtractResponse, HealthResponse

logger = logging.getLogger("reel-extractor")
logging.basicConfig(level=logging.INFO)

VERSION = "1.0.0"

app = FastAPI(
    title="Instagram Reel Knowledge Extractor",
    description=(
        "Extracts all available knowledge from an Instagram reel link: "
        "caption, hashtags, author, engagement, full audio transcript, and "
        "on-screen text."
    ),
    version=VERSION,
    servers=[{"url": os.environ.get("PUBLIC_BASE_URL", "http://localhost:8000")}],
)

# ---------------------------------------------------------------------------
# Auth: simple API-key header, which Custom GPT Actions support natively.
# Set REEL_API_KEY in the environment; leave unset to disable auth (dev only).
# ---------------------------------------------------------------------------
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def require_api_key(key: Optional[str] = Security(api_key_header)) -> None:
    expected = os.environ.get("REEL_API_KEY")
    if expected and key != expected:
        raise HTTPException(status_code=401, detail="Invalid or missing X-API-Key header.")


# ---------------------------------------------------------------------------
# Tiny in-memory LRU cache so repeated questions about the same reel are free.
# ---------------------------------------------------------------------------
_CACHE_MAX = int(os.environ.get("CACHE_SIZE", "64"))
_cache: "OrderedDict[str, dict]" = OrderedDict()


def _cache_get(key: str) -> Optional[dict]:
    if key in _cache:
        _cache.move_to_end(key)
        return _cache[key]
    return None


def _cache_put(key: str, value: dict) -> None:
    _cache[key] = value
    _cache.move_to_end(key)
    while len(_cache) > _CACHE_MAX:
        _cache.popitem(last=False)


@app.get("/health", response_model=HealthResponse, operation_id="health")
def health() -> HealthResponse:
    from .transcribe import MODEL_SIZE

    return HealthResponse(status="ok", whisper_model=MODEL_SIZE, version=VERSION)


@app.post(
    "/extract",
    response_model=ExtractResponse,
    operation_id="extractReel",
    summary="Extract transcript, on-screen text, caption and metadata from an Instagram reel URL",
    dependencies=[Depends(require_api_key)],
)
def extract(req: ExtractRequest) -> ExtractResponse:
    started = time.time()
    try:
        shortcode = parse_shortcode(req.url)
    except InvalidUrlError as e:
        raise HTTPException(status_code=422, detail=str(e))

    cache_key = f"{shortcode}:{req.include_ocr}:{req.language or 'auto'}"
    cached = _cache_get(cache_key)
    if cached:
        return ExtractResponse(**cached)

    notes: list[str] = []
    try:
        data = fetch_reel(req.url, download=True)
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))

    notes.extend(data.notes)
    meta = build_metadata(data)

    transcript_text = None
    segments: list[dict] = []
    detected_language = None
    on_screen: list[str] = []

    if data.video_path:
        try:
            from .transcribe import transcribe

            result = transcribe(data.video_path, language=req.language)
            transcript_text = result["text"]
            segments = result["segments"]
            detected_language = result["language"]
            if not transcript_text:
                notes.append("No speech detected (music-only or silent reel).")
        except Exception as e:  # noqa: BLE001 — degrade gracefully, keep metadata
            logger.exception("Transcription failed")
            notes.append(f"Transcription failed: {e}")

        if req.include_ocr:
            try:
                from .ocr import ocr_video

                on_screen = ocr_video(data.video_path)
            except Exception as e:  # noqa: BLE001
                logger.exception("OCR failed")
                notes.append(f"OCR failed: {e}")

        # Clean up the downloaded video's temp directory.
        shutil.rmtree(os.path.dirname(data.video_path), ignore_errors=True)

    payload = {
        "url": req.url,
        **meta,
        "detected_language": detected_language,
        "transcript": transcript_text,
        "transcript_segments": segments,
        "on_screen_text": on_screen,
        "notes": notes,
    }
    _cache_put(cache_key, payload)
    logger.info("Extracted %s in %.1fs", shortcode, time.time() - started)
    return ExtractResponse(**payload)
