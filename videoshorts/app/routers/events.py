"""
events.py — Server-Sent Events (SSE) router for live progress updates.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from sse_starlette.sse import EventSourceResponse

from app.database import get_db
from app.models.job import Job
from app.services.worker import worker

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1", tags=["events"])


@router.get("/jobs/{job_id}/events")
async def job_events_stream(job_id: str, request: Request, db: Session = Depends(get_db)):
    """
    Stream live progress and log updates for *job_id* using SSE.
    Automatically closes stream when job reaches terminal state ('done', 'failed', 'cancelled').
    """
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    initial_status = str(job.status)
    initial_payload = {
        "job_id": str(job.id),
        "status": initial_status,
        "progress": float(job.progress),
        "step": str(job.current_step) if job.current_step else None,
        "error": str(job.error) if job.error else None,
    }

    async def event_generator() -> AsyncGenerator[dict, None]:
        # Send initial snapshot immediately
        yield {
            "event": "status",
            "data": json.dumps(initial_payload),
        }

        # If job is already terminal, end stream
        if initial_status in ("done", "failed", "cancelled"):
            return

        # Subscribe to worker queue
        queue = worker.subscribe(job_id)
        try:
            while True:
                if await request.is_disconnected():
                    break

                try:
                    # Wait for next event or heartbeat
                    message = await asyncio.wait_for(queue.get(), timeout=15.0)
                    yield {
                        "event": message.get("event", "message"),
                        "data": json.dumps(message.get("data", {})),
                    }
                    if message.get("event") in ("done", "failed", "cancelled"):
                        break
                except asyncio.TimeoutError:
                    # Heartbeat comment to keep connection alive
                    yield {
                        "event": "ping",
                        "data": json.dumps({"timestamp": asyncio.get_event_loop().time()}),
                    }
        finally:
            worker.unsubscribe(job_id, queue)

    return EventSourceResponse(event_generator())
