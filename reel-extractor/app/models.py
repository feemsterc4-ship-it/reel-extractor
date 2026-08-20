"""Pydantic models for the Reel Extractor API."""
from typing import Optional

from pydantic import BaseModel, Field


class ExtractRequest(BaseModel):
    url: str = Field(
        ...,
        description="Instagram reel/post URL, e.g. https://www.instagram.com/reel/ABC123/",
        examples=["https://www.instagram.com/reel/C8xYz123abc/"],
    )
    include_ocr: bool = Field(
        True,
        description="Also OCR on-screen text from sampled video frames (slower).",
    )
    language: Optional[str] = Field(
        None,
        description="Optional ISO language hint for transcription, e.g. 'en', 'de'. "
        "Auto-detected when omitted.",
    )


class AuthorInfo(BaseModel):
    username: Optional[str] = None
    full_name: Optional[str] = None
    profile_url: Optional[str] = None


class Engagement(BaseModel):
    views: Optional[int] = None
    likes: Optional[int] = None
    comments: Optional[int] = None


class TranscriptSegment(BaseModel):
    start: float
    end: float
    text: str


class ExtractResponse(BaseModel):
    url: str
    shortcode: Optional[str] = None
    title: Optional[str] = None
    caption: Optional[str] = None
    hashtags: list[str] = []
    mentions: list[str] = []
    author: AuthorInfo = AuthorInfo()
    engagement: Engagement = Engagement()
    upload_date: Optional[str] = None
    duration_seconds: Optional[float] = None
    detected_language: Optional[str] = None
    transcript: Optional[str] = Field(
        None, description="Full spoken-word transcript of the reel's audio."
    )
    transcript_segments: list[TranscriptSegment] = []
    on_screen_text: list[str] = Field(
        default_factory=list,
        description="Deduplicated text overlays detected in the video frames (OCR).",
    )
    notes: list[str] = Field(
        default_factory=list,
        description="Non-fatal warnings, e.g. 'OCR skipped' or 'login required'.",
    )


class HealthResponse(BaseModel):
    status: str
    whisper_model: str
    version: str
