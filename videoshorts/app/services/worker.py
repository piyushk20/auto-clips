"""
worker.py — Background worker that executes VideoShorts jobs one at a time.

Maintains an in-memory event bus for real-time SSE progress streaming.
Updates SQLite DB state at each step.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Set

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal
from app.models.job import Clip, Job
from app.services import engine
from app.services.engine import EnvError, PipelineError
from app.services.memory_service import memory_service

log = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# Stage keyword matcher to estimate progress
STAGE_PATTERNS = [
    (re.compile(r"download|fetching|fetching video", re.I), "downloading", 0.15),
    (re.compile(r"transcrib|whisper|audio|extract", re.I), "transcribing", 0.35),
    (re.compile(r"analyz|llm|evaluat|score|gemini|prompt", re.I), "analyzing", 0.60),
    (re.compile(r"cut|clip|segment|extracting clips", re.I), "cutting", 0.75),
    (re.compile(r"render|produce|crop|portrait|ffmpeg", re.I), "producing", 0.85),
    (re.compile(r"export|zip|pack", re.I), "exporting", 0.95),
]


def _ensure_english_details(clips: list[engine.ClipInfo]) -> None:
    """Ensure all clip titles and recommendation reasons are in high-engagement English."""
    has_chinese = False
    for c in clips:
        if (c.title and re.search(r"[\u4e00-\u9fff]", c.title)) or (c.reason and re.search(r"[\u4e00-\u9fff]", c.reason)):
            has_chinese = True
            break
    if not has_chinese:
        return

    api_key = settings.get_api_key("gemini")
    if not api_key:
        return

    import urllib.request
    from app.services.memory_service import memory_service
    mem_context = memory_service.get_prompt_context()

    payload_clips = [{"id": i, "title": c.title, "reason": c.reason} for i, c in enumerate(clips)]

    prompt = (
        "You are an expert viral YouTube Shorts / TikTok editor.\n"
        "Translate and rewrite the following clip titles and reasons from Chinese into high-CTR, punchy, engaging ENGLISH.\n"
        f"Input clips:\n{json.dumps(payload_clips, ensure_ascii=False)}\n\n"
        "Requirements:\n"
        "- Titles must be high-engagement English YouTube Shorts titles (under 75 characters).\n"
        "- Reasons must be 1-2 sentence English explanations of why this moment is compelling.\n"
        f"{mem_context}\n"
        "- Return ONLY a valid JSON array of objects with keys: id, title, reason."
    )
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.1-flash-lite:generateContent?key={api_key}"
    req_body = json.dumps({"contents": [{"parts": [{"text": prompt}]}]}).encode("utf-8")
    req = urllib.request.Request(url, data=req_body, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=35) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            text = data["candidates"][0]["content"]["parts"][0]["text"]
            match = re.search(r"\[.*\]", text, re.DOTALL)
            if match:
                items = json.loads(match.group(0))
                by_id = {}
                for it in items:
                    if "id" in it:
                        by_id[it["id"]] = it
                        by_id[str(it["id"])] = it
                        try:
                            by_id[int(it["id"])] = it
                        except Exception:
                            pass
                for i, c in enumerate(clips):
                    matched = by_id.get(i) or by_id.get(str(i))
                    if matched:
                        if matched.get("title"):
                            c.title = matched["title"]
                        if matched.get("reason"):
                            c.reason = matched["reason"]
    except Exception as exc:
        log.warning("Could not automatically translate clips to English: %s", exc)


class JobWorker:
    """Single-concurrency background job processor with SSE pub/sub."""

    def __init__(self) -> None:
        self._subscribers: Dict[str, Set[asyncio.Queue]] = {}
        self._subscribers_lock = threading.Lock()
        self._queue: asyncio.Queue[str] = asyncio.Queue()
        self._current_job_id: str | None = None
        self._stop_event = asyncio.Event()
        self._worker_task: asyncio.Task | None = None

    def start(self) -> None:
        """Initialize worker and mark stale jobs failed."""
        self._cleanup_stale_jobs()
        if self._worker_task is None or self._worker_task.done():
            self._worker_task = asyncio.create_task(self._process_loop())
            log.info("Background job worker started.")

    async def stop(self) -> None:
        """Gracefully stop worker."""
        self._stop_event.set()
        if self._worker_task and not self._worker_task.done():
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass
        log.info("Background job worker stopped.")

    def _cleanup_stale_jobs(self) -> None:
        """Mark any job that was left 'running' on previous server shutdown as failed."""
        with SessionLocal() as db:
            stale_jobs = db.execute(
                select(Job).where(Job.status.in_(["running", "queued"]))
            ).scalars().all()
            for job in stale_jobs:
                job.status = "failed"
                job.error = "Server restarted while job was in progress."
                job.finished_at = _now_iso()
            if stale_jobs:
                db.commit()
                log.info("Cleaned up %d stale jobs from previous run.", len(stale_jobs))

    async def enqueue(self, job_id: str) -> None:
        """Enqueue a job ID for processing."""
        with SessionLocal() as db:
            job = db.get(Job, job_id)
            if job:
                job.status = "queued"
                db.commit()
        await self._queue.put(job_id)
        self.publish(job_id, "queued", {"job_id": job_id, "status": "queued"})

    def subscribe(self, job_id: str) -> asyncio.Queue:
        """Subscribe an SSE client queue to progress events for *job_id*."""
        q: asyncio.Queue = asyncio.Queue(maxsize=100)
        with self._subscribers_lock:
            self._subscribers.setdefault(job_id, set()).add(q)
        return q

    def unsubscribe(self, job_id: str, q: asyncio.Queue) -> None:
        """Unsubscribe an SSE client queue."""
        with self._subscribers_lock:
            if job_id in self._subscribers:
                self._subscribers[job_id].discard(q)
                if not self._subscribers[job_id]:
                    del self._subscribers[job_id]

    def publish(self, job_id: str, event_type: str, data: dict[str, Any]) -> None:
        """Publish an event to all subscribers of *job_id*."""
        with self._subscribers_lock:
            queues = list(self._subscribers.get(job_id, []))
        message = {"event": event_type, "data": data}
        for q in queues:
            try:
                q.put_nowait(message)
            except (asyncio.QueueFull, Exception):
                pass

    def cancel(self, job_id: str) -> None:
        """Cancel a running job and terminate its active engine subprocess."""
        if self._current_job_id == job_id:
            log.info("Terminating active process for cancelled job %s", job_id)
            engine.kill_active_process()
            self._current_job_id = None

    async def _process_loop(self) -> None:
        """Worker loop that consumes one job at a time."""
        while not self._stop_event.is_set():
            try:
                job_id = await self._queue.get()
            except asyncio.CancelledError:
                break

            self._current_job_id = job_id
            try:
                await asyncio.to_thread(self._run_job_sync, job_id)
            except Exception as exc:
                log.exception("Unexpected error executing job %s: %s", job_id, exc)
            finally:
                self._current_job_id = None
                self._queue.task_done()

    def _run_job_sync(self, job_id: str) -> None:
        """Synchronously execute job (runs inside thread pool)."""
        with SessionLocal() as db:
            job = db.get(Job, job_id)
            if not job:
                log.warning("Job %s not found in DB, skipping.", job_id)
                return
            if job.status == "cancelled":
                log.info("Job %s was cancelled before execution.", job_id)
                return

            job_source = str(job.source)
            job_provider = str(job.provider)
            job_category = str(job.category)
            job_platforms = list(job.platforms or ["youtube_shorts"])

            job.status = "running"
            job.started_at = _now_iso()
            job.progress = 0.05
            job.current_step = "initializing"
            db.commit()

        self.publish(job_id, "status", {"status": "running", "progress": 0.05, "step": "initializing"})

        log_lines: list[str] = []

        def on_progress_line(line: str) -> None:
            log_lines.append(line)
            if len(log_lines) > 50:
                log_lines.pop(0)

            # Match keyword for progress
            step = "processing"
            prog = 0.2
            for pattern, step_name, step_prog in STAGE_PATTERNS:
                if pattern.search(line):
                    step = step_name
                    prog = step_prog
                    break

            # Update DB periodically
            with SessionLocal() as s_db:
                s_job = s_db.get(Job, job_id)
                if s_job and s_job.status == "running":
                    s_job.current_step = step
                    if prog > s_job.progress:
                        s_job.progress = prog
                    s_job.set_log_tail(log_lines)
                    s_db.commit()

            self.publish(job_id, "progress", {
                "job_id": job_id,
                "step": step,
                "progress": prog,
                "line": line,
            })

        try:
            # 1. Check if source is a web URL or local uploaded file
            video_file = job_source
            auto_srt = None
            if job_source.startswith("http://") or job_source.startswith("https://"):
                on_progress_line("Source is a web URL. Downloading video via yt-dlp...")
                video_file, auto_srt = engine.download_source(job_source, progress_cb=on_progress_line)
            else:
                on_progress_line(f"Source is a local video file: {Path(job_source).name}")
                embedded_srt = engine.extract_embedded_subtitles(video_file)
                if embedded_srt:
                    auto_srt = embedded_srt
                    on_progress_line(f"Extracted embedded subtitles: {Path(embedded_srt).name}")

            # Ensure any video (uploaded or downloaded) is bounded to 10m to prevent timeouts or 429 quota exhaustion
            video_file, auto_srt = engine.slice_video_if_needed(video_file, auto_srt, progress_cb=on_progress_line)

            # 2. Run main AutoClip analysis
            res = engine.run_job(
                source=video_file,
                srt=auto_srt,
                provider=job_provider,
                progress_cb=on_progress_line,
                category=job_category,
            )

            # 3. Produce clips for requested platforms
            produced_files_by_platform: dict[str, list[str]] = {}

            for plat in job_platforms:
                if plat in engine.SUPPORTED_PLATFORMS:
                    on_progress_line(f"Rendering clips for platform: {plat}...")
                    try:
                        prod_res = engine.produce_clips(
                            source=video_file,
                            platform=plat,
                            project_name=res.project_id or job_id[:8],
                            progress_cb=on_progress_line,
                        )
                        produced_files_by_platform[plat] = prod_res.output_files
                    except Exception as prod_err:
                        log.warning("Platform produce warning for %s: %s (using primary clips)", plat, prod_err)
                        on_progress_line(f"Using primary viral clips for {plat}")

            # 4. Store clips and finish
            with SessionLocal() as db:
                s_job = db.get(Job, job_id)
                if s_job:
                    s_job.project_id = res.project_id
                    s_job.status = "done"
                    s_job.progress = 1.0
                    s_job.current_step = "completed"
                    s_job.finished_at = _now_iso()

                    # Create permanent workspace folder for this job's clips
                    permanent_clips_dir = settings.outputs_dir / "clips" / job_id
                    permanent_clips_dir.mkdir(parents=True, exist_ok=True)
                    # Guarantee all clip titles and descriptions are in English
                    _ensure_english_details(res.clips)

                    # Save Clip records
                    for i, clip_info in enumerate(res.clips):
                        raw_video_path = clip_info.file if (clip_info.file and Path(clip_info.file).exists()) else None
                        # Check if any produced file matches
                        for plat, files in produced_files_by_platform.items():
                            for fpath in files:
                                if clip_info.clip_id in fpath or f"clip_{i+1}" in fpath:
                                    raw_video_path = fpath
                                    break
                            if raw_video_path and raw_video_path != clip_info.file:
                                break

                        # Permanently copy clip to outputs/clips/{job_id}/
                        permanent_video_path = None
                        if raw_video_path and Path(raw_video_path).exists():
                            src_p = Path(raw_video_path)
                            clean_slug = re.sub(r"[^a-zA-Z0-9]+", "_", clip_info.title or "").strip("_")
                            clean_filename = f"clip_{i+1}_{clean_slug[:45]}.mp4" if clean_slug else f"clip_{i+1}_{clip_info.clip_id}.mp4"
                            dst_p = permanent_clips_dir / clean_filename
                            try:
                                import shutil
                                shutil.copy2(src_p, dst_p)
                                permanent_video_path = str(dst_p.resolve())
                            except Exception as copy_err:
                                log.warning("Could not copy clip to permanent outputs: %s", copy_err)
                                permanent_video_path = str(src_p.resolve())

                        # Direct FFmpeg cut fallback if no produced file was generated
                        if not permanent_video_path or not Path(permanent_video_path).exists():
                            ffmpeg_dir = r"C:\Users\HP\ffmpeg\ffmpeg-2026-04-09-git-d3d0b7a5ee-essentials_build\bin"
                            ffmpeg_bin = str(Path(ffmpeg_dir) / "ffmpeg.exe") if (Path(ffmpeg_dir) / "ffmpeg.exe").exists() else "ffmpeg"
                            clean_slug = re.sub(r"[^a-zA-Z0-9]+", "_", clip_info.title or "").strip("_")
                            clean_filename = f"clip_{i+1}_{clean_slug[:45]}.mp4" if clean_slug else f"clip_{i+1}_{clip_info.clip_id}.mp4"
                            dst_p = permanent_clips_dir / clean_filename

                            cut_cmd = [
                                ffmpeg_bin, "-y",
                                "-ss", str(max(0.0, clip_info.start_sec)),
                                "-to", str(clip_info.end_sec),
                                "-i", str(video_file),
                                "-c:v", "libx264", "-c:a", "aac",
                                "-pix_fmt", "yuv420p",
                                str(dst_p)
                            ]
                            try:
                                import subprocess
                                subprocess.run(cut_cmd, capture_output=True, timeout=120)
                                if dst_p.exists() and dst_p.stat().st_size > 1000:
                                    permanent_video_path = str(dst_p.resolve())
                            except Exception as cut_err:
                                log.warning("Direct FFmpeg cut fallback failed for clip %s: %s", clip_info.clip_id, cut_err)

                        new_clip = Clip(
                            job_id=job_id,
                            clip_index=i + 1,
                            clip_id=clip_info.clip_id,
                            title=clip_info.title,
                            score=clip_info.score,
                            start_sec=clip_info.start_sec,
                            end_sec=clip_info.end_sec,
                            duration_sec=clip_info.duration_sec,
                            reason=clip_info.reason,
                            video_path=permanent_video_path,
                        )
                        db.add(new_clip)

                    db.commit()

                    # Record top performing viral clip pattern in Mem0 memory
                    if res.clips:
                        top_clip = max(res.clips, key=lambda c: c.score or 0.0)
                        if (top_clip.score or 0.0) >= 0.85 and top_clip.title:
                            try:
                                memory_service.add_memory(
                                    f"Viral short title pattern that scored {int((top_clip.score or 0)*10)}/10: '{top_clip.title}'. Highlight style: {top_clip.reason}",
                                    metadata={"source": "job_result", "job_id": job_id, "score": top_clip.score}
                                )
                            except Exception as mem_err:
                                log.warning("Could not record viral clip memory in Mem0: %s", mem_err)

            self.publish(job_id, "done", {
                "job_id": job_id,
                "status": "done",
                "progress": 1.0,
                "project_id": res.project_id,
                "clip_count": len(res.clips),
            })

        except (PipelineError, EnvError) as exc:
            log.error("Job %s failed with engine error: %s", job_id, exc)
            with SessionLocal() as db:
                s_job = db.get(Job, job_id)
                if s_job:
                    s_job.status = "failed"
                    s_job.error = str(exc)
                    s_job.finished_at = _now_iso()
                    db.commit()

            self.publish(job_id, "failed", {
                "job_id": job_id,
                "status": "failed",
                "error": str(exc),
            })

        except Exception as exc:
            log.exception("Job %s unexpected failure: %s", job_id, exc)
            with SessionLocal() as db:
                s_job = db.get(Job, job_id)
                if s_job:
                    s_job.status = "failed"
                    s_job.error = f"Internal error: {exc}"
                    s_job.finished_at = _now_iso()
                    db.commit()

            self.publish(job_id, "failed", {
                "job_id": job_id,
                "status": "failed",
                "error": str(exc),
            })


# Global singleton worker
worker = JobWorker()
