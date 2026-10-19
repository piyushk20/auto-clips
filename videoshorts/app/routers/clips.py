"""
clips.py — Router for querying and downloading generated video clips.
"""
from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models.job import Clip, Job

router = APIRouter(prefix="/api/v1", tags=["clips"])


@router.get("/jobs/{job_id}/clips")
def list_job_clips(job_id: str, db: Session = Depends(get_db)) -> dict:
    """List all clips belonging to *job_id*."""
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    return {
        "job_id": job_id,
        "clips": [c.to_dict() for c in job.clips],
    }


@router.get("/clips/{clip_id}")
def get_clip(clip_id: str, db: Session = Depends(get_db)) -> dict:
    """Get single clip metadata."""
    clip = db.get(Clip, clip_id)
    if not clip:
        raise HTTPException(status_code=404, detail="Clip not found")
    return clip.to_dict()


@router.get("/clips/{clip_id}/download")
def download_clip(
    clip_id: str,
    download: bool = Query(False, description="Set to true to force file download dialog"),
    db: Session = Depends(get_db),
):
    """
    Stream or download the generated MP4 file for *clip_id*.
    Enforces strict path traversal prevention.
    """
    clip = db.get(Clip, clip_id)
    if not clip:
        raise HTTPException(status_code=404, detail="Clip not found")

    if not clip.video_path:
        raise HTTPException(status_code=404, detail="No video file has been rendered for this clip yet.")

    path = Path(clip.video_path).resolve()
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Video file not found on disk.")

    # Security check: Ensure file resides within allowed directories
    allowed_roots = [
        settings.outputs_dir.resolve(),
        Path(os.environ.get("APPDATA", "")).resolve(),
    ]
    is_allowed = any(root in path.parents or root == path.parent for root in allowed_roots)
    if not is_allowed:
        raise HTTPException(status_code=403, detail="Access denied: file outside permitted directories.")

    import re
    import urllib.parse
    title_slug = re.sub(r"[^a-zA-Z0-9_\-]+", "_", clip.title or "").strip("_")
    safe_ascii_name = f"{title_slug[:50]}.mp4" if title_slug else f"clip_{clip.clip_index or 1}.mp4"
    encoded_name = urllib.parse.quote(path.name or safe_ascii_name)
    disp_type = "attachment" if download else "inline"
    headers = {
        "Content-Disposition": f'{disp_type}; filename="{safe_ascii_name}"; filename*=UTF-8\'\'{encoded_name}',
        "Accept-Ranges": "bytes",
    }

    return FileResponse(
        path=str(path),
        media_type="video/mp4",
        headers=headers,
    )
