"""
job.py — ORM models for jobs and clips.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

from sqlalchemy import Float, ForeignKey, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_uuid() -> str:
    return str(uuid.uuid4())


class Job(Base):
    """Represents one autoclip pipeline run request."""

    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(Text, primary_key=True, default=_new_uuid)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    # platforms stored as JSON array string: '["tiktok","shorts"]'
    platforms_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    provider: Mapped[str] = mapped_column(Text, nullable=False, default="gemini")
    category: Mapped[str] = mapped_column(Text, nullable=False, default="default")

    # Status: pending | queued | running | done | failed | cancelled
    status: Mapped[str] = mapped_column(Text, nullable=False, default="pending")
    progress: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    current_step: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Last N stderr lines stored as JSON array string
    log_tail_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")

    # Set after autoclip run succeeds
    project_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[str] = mapped_column(Text, nullable=False, default=_now_iso)
    started_at: Mapped[str | None] = mapped_column(Text, nullable=True)
    finished_at: Mapped[str | None] = mapped_column(Text, nullable=True)

    clips: Mapped[list["Clip"]] = relationship("Clip", back_populates="job", cascade="all, delete-orphan")

    # ── helpers ────────────────────────────────────────────────────────────

    @property
    def platforms(self) -> list[str]:
        return json.loads(self.platforms_json)

    @platforms.setter
    def platforms(self, value: list[str]) -> None:
        self.platforms_json = json.dumps(value)

    @property
    def log_tail(self) -> list[str]:
        return json.loads(self.log_tail_json)

    def append_log(self, line: str, max_lines: int = 50) -> None:
        lines = self.log_tail
        lines.append(line)
        self.log_tail_json = json.dumps(lines[-max_lines:])

    def set_log_tail(self, lines: list[str]) -> None:
        self.log_tail_json = json.dumps(lines[-50:])

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "source": self.source,
            "platforms": self.platforms,
            "provider": self.provider,
            "category": self.category,
            "status": self.status,
            "progress": self.progress,
            "current_step": self.current_step,
            "log_tail": self.log_tail,
            "project_id": self.project_id,
            "error": self.error,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "clip_count": len(self.clips),
        }


class Clip(Base):
    """One scored clip segment from a completed job."""

    __tablename__ = "clips"

    id: Mapped[str] = mapped_column(Text, primary_key=True, default=_new_uuid)
    job_id: Mapped[str] = mapped_column(Text, ForeignKey("jobs.id"), nullable=False)
    clip_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # From autoclip run output
    clip_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    start_sec: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    end_sec: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    duration_sec: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    # From autoclip produce output
    platform: Mapped[str | None] = mapped_column(Text, nullable=True)
    video_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    cover_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    zip_path: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[str] = mapped_column(Text, nullable=False, default=_now_iso)

    job: Mapped["Job"] = relationship("Job", back_populates="clips")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "job_id": self.job_id,
            "clip_index": self.clip_index,
            "clip_id": self.clip_id,
            "title": self.title,
            "score": self.score,
            "start_sec": self.start_sec,
            "end_sec": self.end_sec,
            "duration_sec": self.duration_sec,
            "reason": self.reason,
            "platform": self.platform,
            "has_video": self.video_path is not None,
            "has_cover": self.cover_path is not None,
            "has_zip": self.zip_path is not None,
            "created_at": self.created_at,
        }
