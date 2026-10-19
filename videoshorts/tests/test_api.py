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
    }
    response = client.post("/api/v1/jobs", json=payload)
    assert response.status_code == 201
    job = response.json()
    assert "id" in job
    assert job["source"] == payload["source"]
    assert job["platforms"] == ["youtube_shorts", "tiktok"]

    # Fetch job by ID
    get_res = client.get(f"/api/v1/jobs/{job['id']}")
    assert get_res.status_code == 200
    details = get_res.json()
    assert details["id"] == job["id"]
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
    monkeypatch.setenv("MEM0_STORAGE_PATH", ":memory:")
    # Reset singleton memory to pick up test config
    from app.services.memory_service import memory_service
    memory_service._memory = None
    memory_service._init_attempted = False

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
