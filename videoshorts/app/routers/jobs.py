"""
jobs.py — REST API router for managing VideoShorts jobs.
"""
from __future__ import annotations

import ipaddress
import json
import os
import shutil
import urllib.parse
import uuid
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models.job import Clip, Job
from app.services import engine
from app.services.worker import worker

router = APIRouter(prefix="/api/v1", tags=["jobs"])

BLOCKED_HOSTNAMES = {"localhost", "127.0.0.1", "0.0.0.0", "::1", "169.254.169.254"}
ALLOWED_URL_SCHEMES = {"http", "https"}
ALLOWED_VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v"}
MAX_UPLOAD_SIZE = 500 * 1024 * 1024  # 500 MB


def _validate_source(source: str) -> str:
    """Validate input source for SSRF and arbitrary local path traversal."""
    source = source.strip()
    if not source:
        raise HTTPException(status_code=400, detail="Source cannot be empty.")

    if source.startswith("http://") or source.startswith("https://"):
        parsed = urllib.parse.urlparse(source)
        if parsed.scheme.lower() not in ALLOWED_URL_SCHEMES:
            raise HTTPException(status_code=400, detail=f"Unsupported URL scheme: {parsed.scheme}")
        hostname = (parsed.hostname or "").lower()
        if not hostname or hostname in BLOCKED_HOSTNAMES or hostname.endswith(".internal") or hostname.endswith(".local"):
            raise HTTPException(status_code=400, detail=f"Invalid or restricted host: {hostname}")
        try:
            ip = ipaddress.ip_address(hostname)
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
                raise HTTPException(status_code=400, detail="Private or internal IP addresses are not permitted.")
        except ValueError:
            pass  # It is a domain name
        return source
    else:
        # Local file path: must be strictly inside outputs directory
        local_p = Path(source).resolve()
        outputs_root = settings.outputs_dir.resolve()
        if not (outputs_root in local_p.parents or outputs_root == local_p.parent):
            raise HTTPException(status_code=400, detail="Local source files must reside within the outputs directory.")
        if not local_p.is_file():
            raise HTTPException(status_code=400, detail="Specified local video file does not exist.")
        return str(local_p)


class JobCreateRequest(BaseModel):
    source: str = Field(..., description="Video URL or uploaded file path")
    platforms: list[str] = Field(default_factory=lambda: ["youtube_shorts"])
    provider: str = Field(default="gemini")
    category: str = Field(default="default")


@router.get("/health")
def health_check() -> dict:
    """Return health status of API and underlying engines."""
    doctor = engine.check_env()
    return {
        "status": "ok",
        "autoclip_binary": doctor.get("autoclip_bin", False),
        "ffmpeg": doctor.get("ffmpeg", False),
        "provider": settings.autoclip_provider,
        "database": settings.database_url,
    }


@router.get("/platforms")
def list_platforms() -> dict:
    """List platforms supported for video production."""
    return {
        "supported": engine.SUPPORTED_PLATFORMS,
        "presets": engine.EXPORT_PRESETS,
    }


@router.get("/jobs")
def list_jobs(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    only_with_clips: bool = Query(True),
    db: Session = Depends(get_db),
) -> dict:
    """List video jobs. By default only returns jobs with created clips or active in-progress runs."""
    stmt = select(Job)
    if only_with_clips:
        # Exclude failed and cancelled jobs that have no clips
        stmt = stmt.where(
            (Job.clips.any()) | (Job.status.in_(["pending", "running"]))
        ).where(
            ~Job.source.ilike("%watch?v=sample%")
        )
    stmt = stmt.order_by(desc(Job.created_at)).offset(offset).limit(limit)
    jobs = db.execute(stmt).scalars().all()

    if only_with_clips:
        # Strict memory-safe filter: only keep runs with clips or active in-progress runs, exclude dummy test runs
        jobs = [
            j for j in jobs 
            if (len(j.clips) > 0 or j.status in ("pending", "running")) 
            and "sample" not in j.source.lower()
        ]

    return {
        "jobs": [j.to_dict() for j in jobs],
        "count": len(jobs),
        "offset": offset,
        "limit": limit,
    }


@router.post("/jobs", status_code=status.HTTP_201_CREATED)
async def create_job(
    payload: JobCreateRequest,
    db: Session = Depends(get_db),
) -> dict:
    """Create and enqueue a new VideoShorts job from a URL or existing file path."""
    validated_source = _validate_source(payload.source)

    job = Job(
        source=validated_source,
        provider=payload.provider,
        category=payload.category,
    )
    job.platforms = payload.platforms
    db.add(job)
    db.commit()
    db.refresh(job)

    # Enqueue to background worker
    await worker.enqueue(job.id)

    return job.to_dict()


@router.post("/jobs/upload", status_code=status.HTTP_201_CREATED)
async def upload_and_create_job(
    file: UploadFile = File(...),
    platforms: str = Form("[\"youtube_shorts\"]"),
    provider: str = Form("gemini"),
    category: str = Form("default"),
    db: Session = Depends(get_db),
) -> dict:
    """Upload a local video file with size/extension validation and enqueue a job."""
    upload_dir = settings.outputs_dir / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)

    # Sanitize filename and validate extension
    raw_name = Path(file.filename or "uploaded.mp4").name
    ext = Path(raw_name).suffix.lower()
    if ext not in ALLOWED_VIDEO_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported format '{ext}'. Allowed: {sorted(ALLOWED_VIDEO_EXTENSIONS)}",
        )

    file_id = str(uuid.uuid4())[:8]
    clean_stem = "".join(c for c in Path(raw_name).stem if c.isalnum() or c in ("-", "_"))[:50]
    dest_path = upload_dir / f"{file_id}_{clean_stem}{ext}"

    # Stream write with size limit
    size = 0
    with dest_path.open("wb") as buffer:
        while chunk := await file.read(1024 * 1024):  # 1 MB chunk
            size += len(chunk)
            if size > MAX_UPLOAD_SIZE:
                buffer.close()
                dest_path.unlink(missing_ok=True)
                raise HTTPException(
                    status_code=413,
                    detail=f"File exceeds maximum allowed size of {MAX_UPLOAD_SIZE // (1024*1024)} MB",
                )
            buffer.write(chunk)

    import re
    platforms_list: list[str] = []
    try:
        parsed_p = json.loads(platforms)
        if isinstance(parsed_p, list):
            platforms_list = [str(x) for x in parsed_p if str(x) in engine.SUPPORTED_PLATFORMS]
    except Exception:
        pass
    if not platforms_list:
        for p in re.findall(r"[a-zA-Z0-9_]+", platforms):
            if p in engine.SUPPORTED_PLATFORMS:
                platforms_list.append(p)
    if not platforms_list:
        platforms_list = ["youtube_shorts"]

    job = Job(
        source=str(dest_path.resolve()),
        provider=provider,
        category=category,
    )
    job.platforms = platforms_list
    db.add(job)
    db.commit()
    db.refresh(job)

    await worker.enqueue(job.id)
    return job.to_dict()


@router.get("/jobs/{job_id}")
def get_job(job_id: str, db: Session = Depends(get_db)) -> dict:
    """Fetch job status, progress, and all generated clips."""
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    job_dict = job.to_dict()
    job_dict["clips"] = [clip.to_dict() for clip in job.clips]
    return job_dict


@router.post("/jobs/{job_id}/cancel")
def cancel_job(job_id: str, db: Session = Depends(get_db)) -> dict:
    """Cancel a pending, queued, or running job."""
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job.status in ("done", "failed", "cancelled"):
        return {"status": job.status, "message": f"Job is already {job.status}"}

    job.status = "cancelled"
    job.error = "Cancelled by user"
    db.commit()

    worker.cancel(job_id)
    worker.publish(job_id, "cancelled", {"job_id": job_id, "status": "cancelled"})
    return {"status": "cancelled", "job_id": job_id}


@router.delete("/jobs/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_job(job_id: str, db: Session = Depends(get_db)) -> None:
    """Delete a job, its clips, and permanent video files."""
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    # Clean up associated permanent clip folder
    clips_folder = settings.outputs_dir / "clips" / job_id
    if clips_folder.exists():
        shutil.rmtree(clips_folder, ignore_errors=True)

    db.delete(job)
    db.commit()
