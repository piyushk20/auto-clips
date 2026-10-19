"""
test_api.py — API integration tests using FastAPI TestClient.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.database import Base, engine
from app.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.create_all(bind=engine)
    yield
    from app.database import SessionLocal
    from app.models.job import Job
    with SessionLocal() as db:
        test_jobs = db.query(Job).filter(
            (Job.source.ilike("%sample%")) | (Job.source.ilike("%dQw4w9WgXcQ%"))
        ).all()
        for j in test_jobs:
            db.delete(j)
        db.commit()


def test_health_endpoint():
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "autoclip_binary" in data
    assert "ffmpeg" in data


def test_platforms_endpoint():
    response = client.get("/api/v1/platforms")
    assert response.status_code == 200
    data = response.json()
    assert "supported" in data
    assert "youtube_shorts" in data["supported"]


def test_create_and_get_job():
    payload = {
        "source": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "platforms": ["youtube_shorts", "tiktok"],
        "provider": "gemini",
        "category": "podcast",
        "min_score": 0.85,
        "pacing": "punchy",
    }
    response = client.post("/api/v1/jobs", json=payload)
    assert response.status_code == 201
    job = response.json()
    assert "id" in job
    assert job["source"] == payload["source"]
    assert job["platforms"] == ["youtube_shorts", "tiktok"]
    assert job["min_score"] == 0.85
    assert job["pacing"] == "punchy"

    # Fetch job by ID
    get_res = client.get(f"/api/v1/jobs/{job['id']}")
    assert get_res.status_code == 200
    details = get_res.json()
    assert details["id"] == job["id"]
    assert details["min_score"] == 0.85
    assert details["pacing"] == "punchy"
    assert "clips" in details


def test_cancel_job():
    payload = {
        "source": "https://www.youtube.com/watch?v=sample",
        "platforms": ["youtube_shorts"],
    }
    res = client.post("/api/v1/jobs", json=payload)
    job_id = res.json()["id"]

    cancel_res = client.post(f"/api/v1/jobs/{job_id}/cancel")
    assert cancel_res.status_code == 200
    data = cancel_res.json()
    assert data["status"] == "cancelled"


def test_index_page_returns_html():
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "VideoShorts" in response.text


def test_memories_endpoints(monkeypatch):
    from app.services.memory_service import memory_service
    # Mock memory methods for fast and isolated test execution
    dummy_memories = [
        {"id": "mem-1", "memory": "Always prioritize strong emotional hooks in the first 5 seconds.", "created_at": "2026-10-20T00:00:00"}
    ]
    monkeypatch.setattr(memory_service, "get_prompt_context", lambda *a, **kw: "Memory context rules: ...")
    monkeypatch.setattr(memory_service, "add_memory", lambda *a, **kw: {"status": "ok", "results": [{"id": "mem-1"}]})
    monkeypatch.setattr(memory_service, "get_memories", lambda *a, **kw: dummy_memories)
    monkeypatch.setattr(memory_service, "search_memories", lambda *a, **kw: dummy_memories)

    # 1. List / Context
    ctx_res = client.get("/api/v1/memories/context")
    assert ctx_res.status_code == 200
    assert "prompt_context" in ctx_res.json()

    # 2. Add Memory
    add_res = client.post("/api/v1/memories", json={
        "text": "Always prioritize strong emotional hooks in the first 5 seconds.",
        "category": "hook"
    })
    assert add_res.status_code == 200
    data = add_res.json()
    assert data["status"] == "ok"

    # 3. List & Search
    list_res = client.get("/api/v1/memories")
    assert list_res.status_code == 200
    assert "memories" in list_res.json()

    search_res = client.get("/api/v1/memories?q=emotional+hooks")
    assert search_res.status_code == 200
    assert "memories" in search_res.json()

