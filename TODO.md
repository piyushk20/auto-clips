# 📋 Auto-Clips (VideoShorts AI) — Product Roadmap & Detailed TODO

This document tracks completed milestones and planned feature enhancements across the **Auto-Clips** ecosystem.

---

## 🎯 Completed Milestones (Phase 0 — Stable Baseline)

- [x] **FastAPI Backend & Async Job Worker**: Background queue with thread-safe SQLite persistence and graceful error handling.
- [x] **AutoClip Engine Integration**: Subprocess adapter isolating CLI execution with automatic PATH resolution for system FFmpeg.
- [x] **YouTube Ingestion via yt-dlp**: Seamless download of 1080p/720p streams, automated `.srt` extraction, and 10-minute segmenting to guard against 429 quota exhaustion.
- [x] **Multimodal AI Scoring with Gemini**: Integration with `gemini-3.1-flash-lite` and `gemini-1.5-flash` for high-speed viral moment detection and virality scoring (0.00 – 1.00).
- [x] **Automatic 9:16 Vertical Reframing**: Cropping horizontal footage into standard vertical shorts format.
- [x] **Word-Timed Subtitle Burning**: Dynamic subtitle rendering with platform presets (`youtube_shorts`, `tiktok`, `instagram_reels`, `douyin`).
- [x] **Glassmorphic Single-Page Dashboard**: Reactive dark-mode interface with live Server-Sent Events (SSE) streaming progress and status updates.
- [x] **Preview & Download Workflow**: In-browser video player with custom video controls and direct MP4 downloads.
- [x] **Security Hardening**: SSRF defense against cloud metadata endpoints (`169.254.169.254`), path traversal prevention on clip downloads, and file type validation.
- [x] **Comprehensive Test Suite**: 18 unit, integration, and security tests passing.

---

## 🚀 Phase 1: Near-Term Studio & UX Enhancements (Next Release)

### 📦 Batch Processing & Exports
- [ ] **Batch URL Processing**: Allow users to paste a list of YouTube URLs or a YouTube Playlist link for automated queueing.
- [ ] **1-Click "Download All Clips" ZIP**: Endpoint and UI button to bundle all generated shorts for a specific job into a single `.zip` archive.
- [ ] **Webhook Notifications**: Configurable Discord/Slack/Telegram webhook triggers upon job completion.

### 🎨 Subtitle & Visual Customization
- [ ] **Custom Font Uploads**: Allow users to upload `.ttf`/`.otf` fonts (e.g. Montserrat, Anton, The Bold Font, Komika Axis).
- [ ] **Animated Karaoke Subtitles**: Active word highlighting with bounce, color pop, and emoji injection.
- [ ] **Custom Watermark / Logo Overlay**: Option to upload a transparent PNG logo and position it (top-right, top-left, bottom).
- [ ] **Color Themes for Captions**: Presets for classic MrBeast yellow, Alex Hormozi neon green, clean white/black outline, and gradient text.

### ✂️ Interactive Clip Editing
- [ ] **Interactive Waveform Trimmer**: UI slider to fine-tune the start and end timestamp of a selected clip by ±5 seconds.
- [ ] **Manual Reframing Selector**: Canvas overlay allowing users to drag the 9:16 bounding box if auto-tracking misses the speaker.

---

## 🧠 Phase 2: Advanced AI & Video Processing

### 🎙️ Audio & Speech Intelligence
- [ ] **Local Whisper Fallback**: Self-hosted `faster-whisper` integration for offline speech-to-text when YouTube captions or cloud APIs are unavailable.
- [ ] **Silence & Filler Word Removal**: Automatic removal of awkward pauses ("uh", "um", dead air > 1.2s) before final render.
- [ ] **Audio Normalization & Loudness Mastering**: EBU R128 loudness normalization and background noise suppression via FFmpeg `afftdn` or DeepFilterNet.

### 🤖 Multi-Speaker & Visual Intelligence
- [ ] **Multi-Speaker Active Speaker Detection (ASD)**: Auto-switch camera crop between multiple conversational partners in podcasts.
- [ ] **Split-Screen Dynamic Layout**: Automatically generate dual stacked layout (top: speaker 1, bottom: speaker 2 or gameplay) for podcasts and reaction videos.
- [ ] **Auto B-Roll Injection**: Query Pexels/Pixabay APIs based on spoken keywords and overlay relevant B-roll footage to increase visual retention.
- [ ] **Dynamic Punch-In Zoom**: Periodic subtle zoom-ins (1.05x – 1.15x) on key emphasis words to maintain viewer engagement.

---

## 📲 Phase 3: Direct Social Publishing & Integrations

- [ ] **YouTube Data API v3 Integration**: One-click upload to YouTube Shorts with auto-populated viral title, description, and hashtags.
- [ ] **TikTok Content Posting API**: Direct scheduled draft posting to connected TikTok accounts.
- [ ] **Instagram Graph API**: Publish directly to Instagram Reels with custom caption formatting.
- [ ] **Content Calendar & Scheduler**: Queue clips to be published at optimal engagement hours throughout the week.

---

## 🏢 Phase 4: Production Architecture & Scalability

### ⚡ Distributed Worker Infrastructure
- [ ] **Redis + Celery / RQ Queue**: Replace internal Python threading with distributed workers capable of running across multiple GPU worker nodes.
- [ ] **GPU Acceleration**: Add hardware acceleration flags for FFmpeg (`h264_nvenc`, `hevc_nvenc`, `cuda`, `qsv`, `videotoolbox`).
- [ ] **Cloud Object Storage (S3 / R2)**: Migrate local `outputs/` storage to AWS S3 or Cloudflare R2 with signed CDN download URLs.

### 🐳 Containerization & Deployment
- [ ] **Production Dockerfile**: Multi-stage Docker image packaging Python 3.10, FFmpeg, and AutoClip wheel with minimal image footprint.
- [ ] **Docker Compose**: Orchestration file for FastAPI app, Redis, and Celery worker.
- [ ] **One-Click Deployments**: Template configurations for Railway, Render, Fly.io, and AWS ECS.

### 🔐 Multi-Tenancy & Authentication
- [ ] **User Authentication**: JWT / OAuth2 authentication (Google & GitHub login).
- [ ] **Project Workspaces**: Multi-tenant separation of clip libraries and shared team projects.
- [ ] **Rate Limiting & Usage Quotas**: Tier-based quota management for rendering hours.

---

## 📊 Phase 5: Analytics & Growth Intelligence

- [ ] **AI Title & Hook Generator**: Generate 5 high-converting YouTube Shorts / TikTok titles per clip.
- [ ] **Viral Thumbnail Snapper**: AI-selected frame extraction with auto-added high-contrast headline text.
- [ ] **Audience Retention Simulator**: Predict potential drop-off points based on speech pacing and energy analysis.
- [ ] **Social Performance Tracking**: Fetch views, likes, and watch time back into the dashboard via social APIs to learn which scoring criteria perform best.

---

## 🛠️ Phase 6: Code Quality & Developer Experience

- [ ] **GitHub Actions CI/CD Pipeline**: Automated linting (`ruff`, `black`), type checking (`mypy`), and pytest runs on every push and PR.
- [ ] **OpenAPI / Swagger Client Generation**: Generate TypeScript client for third-party integrations.
- [ ] **Comprehensive Documentation Site**: Setup documentation using MkDocs Material or Mintlify.
- [ ] **Pre-commit Hooks**: Enforce security checks and conventional commit formatting.

---

*Contributions are welcome! Please open an issue or pull request referencing the relevant phase item above.*
