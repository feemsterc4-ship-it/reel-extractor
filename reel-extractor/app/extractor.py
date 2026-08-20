"""Download an Instagram reel and pull out its metadata using yt-dlp."""
from __future__ import annotations

import os
import re
import tempfile
from dataclasses import dataclass, field
from typing import Any, Optional

from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError

REEL_URL_RE = re.compile(
    r"https?://(?:www\.)?instagram\.com/(?:[A-Za-z0-9_.]+/)?(?:reel|reels|p|tv)/([A-Za-z0-9_-]+)"
)
HASHTAG_RE = re.compile(r"#([\wÀ-￿]+)")
MENTION_RE = re.compile(r"@([A-Za-z0-9_.]+)")
ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


class InvalidUrlError(ValueError):
    """Raised when the URL is not a recognizable Instagram reel/post URL."""


@dataclass
class ReelData:
    shortcode: Optional[str]
    video_path: Optional[str]
    info: dict[str, Any] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)


def parse_shortcode(url: str) -> str:
    """Validate the URL and return the reel shortcode."""
    m = REEL_URL_RE.match(url.strip())
    if not m:
        raise InvalidUrlError(
            "That doesn't look like an Instagram reel/post URL. Expected something "
            "like https://www.instagram.com/reel/<shortcode>/"
        )
    return m.group(1)


def extract_hashtags(caption: str) -> list[str]:
    return list(dict.fromkeys(HASHTAG_RE.findall(caption or "")))


def extract_mentions(caption: str) -> list[str]:
    return list(dict.fromkeys(MENTION_RE.findall(caption or "")))


def _ydl_opts(workdir: str, download: bool) -> dict[str, Any]:
    opts: dict[str, Any] = {
        "outtmpl": os.path.join(workdir, "%(id)s.%(ext)s"),
        "format": "mp4/best",
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "skip_download": not download,
        "socket_timeout": 20,
        "retries": 2,
    }
    cookie_file = os.environ.get("IG_COOKIES_FILE")
    if cookie_file and os.path.exists(cookie_file):
        opts["cookiefile"] = cookie_file
    return opts


def fetch_reel(url: str, download: bool = True) -> ReelData:
    """Fetch metadata (and optionally the video file) for a reel.

    Returns a ReelData whose ``video_path`` points at the downloaded mp4
    inside a temp directory. The caller is responsible for cleaning up the
    directory (it is created with mkdtemp under REEL_WORKDIR or the system
    temp dir).
    """
    shortcode = parse_shortcode(url)
    workdir = tempfile.mkdtemp(prefix=f"reel_{shortcode}_", dir=os.environ.get("REEL_WORKDIR"))
    data = ReelData(shortcode=shortcode, video_path=None)

    try:
        with YoutubeDL(_ydl_opts(workdir, download)) as ydl:
            info = ydl.extract_info(url, download=download)
    except DownloadError as e:
        msg = ANSI_RE.sub("", str(e))
        lowered = msg.lower()
        if "no video formats" in lowered:
            raise RuntimeError(
                "This link is a photo post or image carousel — there's no video "
                "to transcribe. This tool extracts reels/video posts; try a link "
                "like https://www.instagram.com/reel/<shortcode>/"
            ) from e
        if "login" in lowered or "rate" in lowered:
            raise RuntimeError(
                "Instagram refused the request (login wall or rate limit). "
                "Configure IG_COOKIES_FILE with an exported cookies.txt from a "
                "logged-in browser session, or try again later."
            ) from e
        raise RuntimeError(f"Could not fetch the reel: {msg}") from e

    if info is None:
        raise RuntimeError("yt-dlp returned no data for this URL.")

    data.info = info
    if download:
        requested = info.get("requested_downloads") or []
        if requested and requested[0].get("filepath"):
            data.video_path = requested[0]["filepath"]
        else:
            # Fall back to scanning the workdir.
            files = [
                os.path.join(workdir, f)
                for f in os.listdir(workdir)
                if f.lower().endswith((".mp4", ".webm", ".mkv", ".mov"))
            ]
            data.video_path = files[0] if files else None
        if not data.video_path:
            data.notes.append("Video file was not downloaded; transcript/OCR unavailable.")
    return data


def build_metadata(data: ReelData) -> dict[str, Any]:
    """Map yt-dlp info to the fields the API returns."""
    info = data.info
    caption = info.get("description") or ""
    username = info.get("uploader_id") or info.get("channel") or info.get("uploader")
    upload_date = info.get("upload_date")  # YYYYMMDD
    if upload_date and len(upload_date) == 8:
        upload_date = f"{upload_date[:4]}-{upload_date[4:6]}-{upload_date[6:]}"
    return {
        "shortcode": data.shortcode,
        "title": info.get("title"),
        "caption": caption or None,
        "hashtags": extract_hashtags(caption),
        "mentions": extract_mentions(caption),
        "author": {
            "username": username,
            "full_name": info.get("uploader"),
            "profile_url": f"https://www.instagram.com/{username}/" if username else None,
        },
        "engagement": {
            "views": info.get("view_count"),
            "likes": info.get("like_count"),
            "comments": info.get("comment_count"),
        },
        "upload_date": upload_date,
        "duration_seconds": info.get("duration"),
    }
