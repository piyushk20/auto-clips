"""
main.py — FastAPI application factory for VideoShorts.
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.database import Base, engine as db_engine
from app.routers import clips, events, jobs, memories
from app.services.worker import worker

logging.basicConfig(
    level=logging.INFO if not settings.debug else logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("videoshorts")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: database initialization and worker lifecycle."""
    log.info("Starting VideoShorts application...")

    # Ensure output and upload directories exist
    settings.outputs_dir.mkdir(parents=True, exist_ok=True)
    (settings.outputs_dir / "uploads").mkdir(parents=True, exist_ok=True)

    # Initialize DB tables
    Base.metadata.create_all(bind=db_engine)

    # Start background worker
    worker.start()
    log.info("VideoShorts ready on http://%s:%d", settings.host, settings.port)

    yield

    # Shutdown background worker
    log.info("Shutting down worker...")
    await worker.stop()
    log.info("VideoShorts shutdown complete.")


app = FastAPI(
    title="VideoShorts",
    description="Automated AI-powered short-form video generation from long videos using AutoClip and LLMs.",
    version="1.0.0",
    lifespan=lifespan,
)


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    """Inject modern HTTP security headers on all responses."""
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com; "
        "media-src 'self' blob: data:; "
        "img-src 'self' data: https:; "
        "connect-src 'self'"
    )
    return response


# Hardened CORS policy
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:8000",
        "http://localhost:8000",
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# Include API routers
app.include_router(jobs.router)
app.include_router(events.router)
app.include_router(clips.router)
app.include_router(memories.router)

# Mount static assets if static folder exists
static_path = Path(__file__).parent / "static"
static_path.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_path)), name="static")


@app.get("/", response_class=HTMLResponse)
async def index_view():
    """Serve the single-page dashboard."""
    templates_path = Path(__file__).parent / "templates" / "index.html"
    if templates_path.exists():
        return HTMLResponse(content=templates_path.read_text(encoding="utf-8"))
    return HTMLResponse(content="<h1>VideoShorts is Running</h1><p>Visit <a href='/docs'>/docs</a> for the API.</p>")
