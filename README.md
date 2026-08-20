# reel-extractorInstagram Reel Knowledge Extractor — Custom GPT Action
Paste a reel link into your Custom GPT and it gets back everything the reel
contains: the full spoken-word transcript (local Whisper, free), the
on-screen text overlays (OCR), the caption, hashtags, mentions,
author, engagement stats, and upload date — as clean JSON it can reason over.
Classic ChatGPT plugins were retired by OpenAI; this project targets their
replacement, Custom GPT Actions: you host this small API anywhere, point
your GPT's Action at it, and ChatGPT calls it whenever a user pastes a reel
link.
How it works
```
reel URL ──> yt-dlp (download + metadata)
                 ├──> faster-whisper ──> transcript (+ timestamps, language)
                 ├──> ffmpeg frames ──> tesseract ──> on-screen text
                 └──> caption / hashtags / author / stats
                                   │
                                   └──> one JSON response to ChatGPT
```
1. Run it locally first
Requires Python 3.11–3.13, `ffmpeg`, and `tesseract-ocr` on your PATH.
(Avoid the very newest Python release — `faster-whisper` sometimes lags on
prebuilt packages for it.)
Windows (PowerShell)
```powershell
winget install Gyan.FFmpeg
winget install UB-Mannheim.TesseractOCR
# close and reopen PowerShell so PATH updates; if tesseract still isn't
# found, add C:\Program Files\Tesseract-OCR to your PATH manually

python -m pip install -r requirements.txt
python -m uvicorn app.main:app --port 8000
```
Test it from a second PowerShell window (note: in PowerShell `curl` is an
alias for Invoke-WebRequest, so use this instead):
```powershell
Invoke-RestMethod -Method Post -Uri http://localhost:8000/extract -ContentType 'application/json' -Body '{"url": "https://www.instagram.com/reel/SHORTCODE/"}'
```
macOS / Linux
```bash
pip install -r requirements.txt
uvicorn app.main:app --port 8000
```
Test it:
```bash
curl -X POST http://localhost:8000/extract \
  -H 'Content-Type: application/json' \
  -d '{"url": "https://www.instagram.com/reel/SHORTCODE/"}'
```
The first request downloads the Whisper model (~150 MB for `base`), so it's
slow once, then fast.
2. Deploy it
Any host that runs a Docker container works — Railway, Render, Fly.io, a VPS.
The Dockerfile installs ffmpeg + tesseract and pre-bakes the Whisper model so
cold starts are quick.
```bash
docker build -t reel-extractor .
docker run -p 8000:8000 \
  -e REEL_API_KEY=$(openssl rand -hex 24) \
  -e PUBLIC_BASE_URL=https://your-app.example.com \
  reel-extractor
```
Environment variables are documented in `.env.example`. The two that matter:
`REEL_API_KEY` — a long random secret. The API rejects requests without it.
`PUBLIC_BASE_URL` — your deployed HTTPS URL (ChatGPT requires HTTPS).
Sizing tip: transcription runs on CPU. `WHISPER_MODEL=base` transcribes a
60-second reel in roughly 15–30 s on a small cloud instance; use `tiny` if you
need faster responses (ChatGPT Actions time out around 45 s), or `small` for
better accuracy if your host is beefy. Setting `"include_ocr": false` in a
request skips the OCR pass and saves several seconds.
3. Wire it into a Custom GPT
ChatGPT → Explore GPTs → Create (requires ChatGPT Plus).
Configure tab → name it (e.g. "Reel Scholar") → paste the contents of
`gpt_instructions.md` into Instructions.
Scroll to Actions → Create new action.
Paste the contents of `openapi.yaml` into the schema box, replacing
`https://YOUR-DEPLOYED-URL-HERE` with your deployed URL.
(Alternatively, "Import from URL" using `https://your-app/openapi.json`,
which the server generates automatically.)
Authentication → API Key → Auth type "Custom" → header name `X-API-Key`
→ paste the same value you set as `REEL_API_KEY`.
Save. Test by pasting a reel link into the GPT's chat.
API
`POST /extract` with `{"url": "...", "include_ocr": true, "language": null}`
returns:
field	meaning
`transcript` / `transcript_segments`	spoken words, full text + timestamped segments
`on_screen_text`	deduplicated text overlays from the video frames
`caption`, `hashtags`, `mentions`	the post text
`author`, `engagement`, `upload_date`, `duration_seconds`	metadata
`detected_language`	Whisper's language detection
`notes`	non-fatal warnings (no speech, OCR failed, login wall…)
`GET /health` reports status and the loaded Whisper model. Results are cached
in memory per reel, so asking follow-up questions about the same link is
instant.
Instagram login walls & rate limits
Public reels usually work anonymously, but Instagram sometimes demands a
login or rate-limits datacenter IPs. If you see a 502 mentioning a login
wall: export cookies from a logged-in browser session (any "cookies.txt"
browser extension, Netscape format), mount the file on your server, and set
`IG_COOKIES_FILE=/path/to/cookies.txt`. Consider a throwaway account —
automated access is against Instagram's Terms of Use, so use this for
personal/fair-use purposes at your own judgment, keep volume low, and don't
redistribute downloaded content.
Project layout
```
app/main.py        FastAPI app, auth, caching, orchestration
app/extractor.py   yt-dlp download + metadata mapping
app/transcribe.py  faster-whisper speech-to-text
app/ocr.py         ffmpeg frame sampling + tesseract OCR
openapi.yaml       schema to paste into the Custom GPT Action
gpt_instructions.md  system prompt for the Custom GPT
Dockerfile         deployable image (ffmpeg + tesseract + model pre-baked)
```
