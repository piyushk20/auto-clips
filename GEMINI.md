# VideoShorts AI — Application Baseline & Stable State

## 🚀 App Overview
VideoShorts AI is a full-stack web application wrapping the AutoClip engine (`https://zhouxiaoka.github.io/autoclip_intro/`) and `yt-dlp` to generate viral short videos from YouTube URLs or local video uploads. It scores clips with Google Gemini, renders 9:16 vertical shorts with subtitles, and provides a real-time reactive dashboard with live SSE streaming, video preview player, and MP4 downloads.

## 📌 Last Known Functional State (2026-10-17)

- **Workspace**: `c:\Users\HP\Auto-clips\videoshorts`
- **Engine Binary**: `c:\Users\HP\Auto-clips\autoclip-venv\Scripts\autoclip.exe`
- **Virtual Environment**: `c:\Users\HP\Auto-clips\videoshorts\.venv`
- **Port**: 8000 (`http://127.0.0.1:8000`)
- **System FFmpeg**: `C:\Users\HP\ffmpeg\ffmpeg-2026-04-09-git-d3d0b7a5ee-essentials_build\bin` (auto-injected into `PATH`)
- **Active LLM Model**: `gemini-3.1-flash-lite` (supports long context with high RPM and fresh daily quota)
- **Downloader**: `yt-dlp[default]` with `'format': 'bestvideo+bestaudio/best'`, automatic SRT extraction, and 10-minute segment slicing for long videos to prevent API 429 quota exhaustion.

## ⚙️ Verified Working Launch Commands

```powershell
cd c:\Users\HP\Auto-clips\videoshorts
& ".\.venv\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

## 🌐 Verified Endpoints
- `GET http://127.0.0.1:8000/` — Main Single Page Web Dashboard
- `GET http://127.0.0.1:8000/api/v1/health` — Returns `{"status":"ok","autoclip_binary":true,"ffmpeg":true}`
- `GET http://127.0.0.1:8000/api/v1/jobs` — Lists all jobs with status and clip count
- `GET http://127.0.0.1:8000/api/v1/jobs/{job_id}` — Job details with log tail and scored clips
- `GET http://127.0.0.1:8000/api/v1/jobs/{job_id}/events` — Server-Sent Events (SSE) real-time stream
- `GET http://127.0.0.1:8000/api/v1/clips/{clip_id}/download` — Streams and downloads rendered MP4 video
