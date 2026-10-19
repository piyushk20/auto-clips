# 🎬 Auto-Clips (VideoShorts AI)

<div align="center">

![Python](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.110%2B-009688?logo=fastapi&logoColor=white)
![Google Gemini](https://img.shields.io/badge/AI-Google%20Gemini%20Flash-4285F4?logo=google&logoColor=white)
![FFmpeg](https://img.shields.io/badge/FFmpeg-5.0%2B-007808?logo=ffmpeg&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-green.svg)
![Status](https://img.shields.io/badge/Status-Active%20%26%20Tested-success)

**Autonomous AI studio that transforms long videos and YouTube links into viral 9:16 vertical shorts with animated subtitles.**

[Features](#-key-features) • [Architecture](#-architecture) • [Getting Started](#-getting-started) • [API Reference](#-api-reference) • [Roadmap](TODO.md)

</div>

---

## 🌟 Overview

**Auto-Clips** is a full-stack, automated video intelligence application that takes long-form video content (podcasts, interviews, webinars, gaming streams, tutorials) or YouTube URLs, identifies the most engaging and viral moments using **Google Gemini multimodal AI**, crops them into **9:16 vertical format**, and burns dynamic, word-timed subtitles tailored for **YouTube Shorts**, **TikTok**, and **Instagram Reels**.

It features a reactive dark-mode web dashboard powered by **FastAPI** with real-time **Server-Sent Events (SSE)** progress tracking, an interactive clip preview player, and instant MP4 downloads.

---

## ✨ Key Features

- 🔗 **Direct YouTube Ingestion**: Powered by `yt-dlp` integration with automatic subtitle extraction, fallback transcription, and automatic 10-minute segmenting for long videos to prevent quota exhaustion.
- 📁 **Local Video Drag-and-Drop**: Upload MP4, MOV, MKV, WebM, and AVI videos directly through the web UI.
- 🧠 **Multimodal Viral AI Scoring**: Powered by `gemini-3.1-flash-lite` / `gemini-1.5-flash`. The model evaluates:
  - **Hook Strength** (first 3-5 seconds engagement)
  - **Narrative Arc & Clarity** (standalone comprehension)
  - **Emotional Impact & Virality Potential** (0.00 – 1.00 score)
  - **Pacing & Punchiness**
- 📐 **Smart 9:16 Vertical Reframing**: Converts standard 16:9 widescreen video to 9:16 portrait using intelligent framing via the AutoClip engine.
- 💬 **Dynamic Timed Subtitles**: Word-level synchronised subtitles with high-contrast styling and customizable font presets.
- 📱 **Multi-Platform Presets**: Custom output tuning for:
  - **YouTube Shorts** (`youtube_shorts`)
  - **TikTok** (`tiktok`)
  - **Instagram Reels** (`instagram_reels`)
  - **Douyin** (`douyin`)
- ⚡ **Reactive Real-Time Dashboard**:
  - Live progress bars and real-time logs via Server-Sent Events (SSE).
  - Built-in video player to preview generated vertical shorts.
  - One-click individual or bulk MP4 downloads.
  - Job history and state persistence in SQLite.
- 🛡️ **Enterprise-Grade Security**:
  - Full SSRF protection against internal/metadata IPs.
  - Strict path traversal prevention.
  - Subprocess timeouts and process tree cleanup.
  - Validated file upload headers and MIME checks.

---

## 🏗️ Architecture

```mermaid
flowchart TD
    User([User / Browser]) <-->|HTTP / SSE Stream| API[FastAPI Web Application\napp/main.py]
    
    subgraph Core Studio Application [videoshorts/]
        API --> DB[(SQLite Database\nvideoshorts.db)]
        API --> Worker[Async Background Worker\napp/services/worker.py]
        Worker --> EngineService[Engine Service Gateway\napp/services/engine.py]
    end

    subgraph External Processing
        EngineService -->|Download / Stream| YTDLP[yt-dlp]
        EngineService -->|Transcribe & Score| Gemini[Google Gemini LLM]
        EngineService -->|Subprocess CLI| AutoClip[AutoClip Engine\nautoclip-venv]
        AutoClip -->|Transcode & Crop| FFmpeg[System FFmpeg]
    end

    AutoClip -->|Generated Shorts| Storage[outputs/clips/{job_id}/]
    Storage -->|Stream & Download| API
```

---

## 📁 Repository Structure

```text
Auto-clips/
├── autoclip-1.5.6-py3-none-any.whl  # Core AutoClip engine Python package
├── GEMINI.md                        # Application state & agent operational baseline
├── README.md                        # Project documentation (this file)
├── TODO.md                          # Detailed roadmap & upcoming features
├── .gitignore                       # Clean Git exclusion rules
│
└── videoshorts/                     # Main Web Application & Service
    ├── app/
    │   ├── main.py                  # FastAPI entry point, middleware & lifespan
    │   ├── config.py                # Environment configuration & settings
    │   ├── database.py              # SQLAlchemy database setup & session
    │   ├── models.py                # Job, Clip, and Event database models
    │   ├── routers/
    │   │   ├── jobs.py              # Job creation, listing, cancellation & upload
    │   │   ├── clips.py             # Clip retrieval & MP4 streaming/download
    │   │   ├── events.py            # SSE real-time event streaming
    │   │   └── memories.py          # App state persistence & memory endpoint
    │   ├── services/
    │   │   ├── engine.py            # Subprocess wrapper for AutoClip CLI & yt-dlp
    │   │   └── worker.py            # Background job processing queue
    │   ├── static/                  # CSS styles, icons, fonts
    │   └── templates/
    │       └── index.html           # Glassmorphic single-page studio dashboard
    ├── scripts/                     # Maintenance, migration & worker scripts
    ├── tests/
    │   ├── test_api.py              # API endpoint & SSE route tests
    │   ├── test_engine.py           # Engine subprocess & error handling tests
    │   └── test_security.py         # SSRF, path traversal & upload security tests
    ├── pytest.ini                   # Pytest configuration
    ├── requirements.txt             # App dependencies
    └── .env.example                 # Sample environment variables
```

---

## 🚀 Getting Started

### 1. Prerequisites
- **Python**: Version 3.10 or higher.
- **FFmpeg**: FFmpeg 5.0+ installed and accessible in your system `PATH` (e.g. `ffmpeg -version`).
- **Google Gemini API Key**: Obtain a free or paid API key from [Google AI Studio](https://aistudio.google.com/).

### 2. Environment Setup

#### Step A: Set Up the AutoClip Engine Virtual Environment
The AutoClip processing engine runs in an isolated virtual environment at the repository root:

```bash
# From the root directory: Auto-clips/
python -m venv autoclip-venv

# Activate the venv:
# On Windows (PowerShell):
.\autoclip-venv\Scripts\Activate.ps1
# On Linux / macOS:
source autoclip-venv/bin/activate

# Install the included AutoClip engine wheel:
pip install autoclip-1.5.6-py3-none-any.whl

# Verify the CLI is available:
autoclip --version
deactivate
```

#### Step B: Set Up the Web Application
```bash
# Navigate into the videoshorts directory:
cd videoshorts

# Create and activate project virtual environment:
python -m venv .venv

# On Windows (PowerShell):
.\.venv\Scripts\Activate.ps1
# On Linux / macOS:
source .venv/bin/activate

# Install application dependencies:
pip install -r requirements.txt
```

### 3. Configure Environment Variables
Copy `.env.example` to `.env` inside `videoshorts/`:

```bash
cp .env.example .env
```

Edit `.env` with your settings:
```ini
# Google Gemini API Key
GEMINI_API_KEY=your_gemini_api_key_here

# Engine & FFmpeg binary paths (Windows example):
AUTOCLIP_BIN=../autoclip-venv/Scripts/autoclip.exe
FFMPEG_PATH=C:/Users/HP/ffmpeg/ffmpeg-2026-04-09-git-d3d0b7a5ee-essentials_build/bin

# Server Configuration
HOST=127.0.0.1
PORT=8000
DEBUG=false
```

---

## 🏃 Running the Application

Start the FastAPI application with Uvicorn:

```bash
cd videoshorts
& ".\.venv\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Open your browser and navigate to:
👉 **`http://127.0.0.1:8000/`**

---

## 📡 API Reference

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/` | Web Studio Single-Page Dashboard |
| `GET` | `/api/v1/health` | System health check (`autoclip_binary`, `ffmpeg`, DB) |
| `GET` | `/api/v1/jobs/platforms` | List of supported social media presets |
| `GET` | `/api/v1/jobs` | List past video generation jobs |
| `POST` | `/api/v1/jobs` | Submit a new YouTube URL or file for clipping |
| `POST` | `/api/v1/jobs/upload` | Upload a local video file |
| `GET` | `/api/v1/jobs/{job_id}` | Get status, logs, and clip metadata for a job |
| `POST` | `/api/v1/jobs/{job_id}/cancel` | Cancel an ongoing processing job |
| `GET` | `/api/v1/jobs/{job_id}/events` | Real-time Server-Sent Events (SSE) progress stream |
| `GET` | `/api/v1/clips/{clip_id}/download` | Stream and download rendered MP4 vertical short |

---

## 🧪 Testing

The test suite covers API routes, subprocess mocking, error handling, SSRF protections, and file traversal hardening.

Run the full test suite:
```bash
cd videoshorts
pytest -v
```

All 18 unit and security tests should pass:
```text
tests/test_api.py::test_health_endpoint PASSED                           [  5%]
tests/test_api.py::test_platforms_endpoint PASSED                        [ 11%]
tests/test_api.py::test_create_and_get_job PASSED                        [ 16%]
tests/test_api.py::test_cancel_job PASSED                                [ 22%]
tests/test_api.py::test_index_page_returns_html PASSED                   [ 27%]
tests/test_api.py::test_memories_endpoints PASSED                        [ 33%]
tests/test_engine.py::test_platforms_list PASSED                         [ 38%]
tests/test_engine.py::test_produce_clips_unsupported_platform PASSED     [ 44%]
tests/test_engine.py::test_run_job_success PASSED                        [ 50%]
tests/test_engine.py::test_run_job_pipeline_error_exit_1 PASSED          [ 55%]
tests/test_engine.py::test_run_job_env_error_exit_2 PASSED               [ 61%]
tests/test_engine.py::test_missing_binary_raises_env_error PASSED        [ 66%]
tests/test_security.py::test_security_headers_present PASSED             [ 72%]
tests/test_security.py::test_ssrf_blocked_localhost PASSED               [ 77%]
tests/test_security.py::test_ssrf_blocked_cloud_metadata PASSED          [ 83%]
tests/test_security.py::test_path_traversal_local_source_blocked PASSED  [ 88%]
tests/test_security.py::test_unsupported_file_upload_blocked PASSED      [ 94%]
tests/test_security.py::test_clip_download_path_traversal_blocked PASSED [100%]

============================= 18 passed in 15.33s =============================
```

---

## 📄 License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.
