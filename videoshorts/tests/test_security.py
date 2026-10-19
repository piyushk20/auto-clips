"""
test_security.py — Automated security test suite for VideoShorts AI.
Tests path traversal, SSRF prevention, safe uploads, and security headers.
"""
import io
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.database import Base, SessionLocal, engine
from app.models.job import Job, Clip


client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.create_all(bind=engine)
    yield


def test_security_headers_present():
    """Verify modern HTTP security headers are present on responses."""
    res = client.get("/api/v1/health")
    assert res.status_code == 200
    assert res.headers.get("x-content-type-options") == "nosniff"
    assert res.headers.get("x-frame-options") == "SAMEORIGIN"
    assert "default-src" in res.headers.get("content-security-policy", "")


def test_ssrf_blocked_localhost():
    """Verify private/loopback URLs are blocked from job creation."""
    payload = {
        "source": "http://127.0.0.1:8000/admin",
        "platforms": ["youtube_shorts"],
    }
    res = client.post("/api/v1/jobs", json=payload)
    assert res.status_code == 400
    assert "restricted" in res.json()["detail"].lower() or "private" in res.json()["detail"].lower()


def test_ssrf_blocked_cloud_metadata():
    """Verify AWS/GCP metadata service IP is blocked."""
    payload = {
        "source": "http://169.254.169.254/latest/meta-data/",
        "platforms": ["youtube_shorts"],
    }
    res = client.post("/api/v1/jobs", json=payload)
    assert res.status_code == 400


def test_path_traversal_local_source_blocked():
    """Verify local files outside outputs/ directory are rejected."""
    payload = {
        "source": "C:\\Windows\\System32\\drivers\\etc\\hosts",
        "platforms": ["youtube_shorts"],
    }
    res = client.post("/api/v1/jobs", json=payload)
    assert res.status_code == 400
    assert "outputs directory" in res.json()["detail"]


def test_unsupported_file_upload_blocked():
    """Verify malicious non-video extensions (.exe, .sh, .py) are rejected."""
    fake_file = io.BytesIO(b"malicious script")
    res = client.post(
        "/api/v1/jobs/upload",
        files={"file": ("exploit.sh", fake_file, "text/x-shellscript")},
    )
    assert res.status_code == 400
    assert "Unsupported format" in res.json()["detail"]


def test_clip_download_path_traversal_blocked():
    """Verify arbitrary path traversal in clip download is blocked with 403."""
    with SessionLocal() as db:
        job = Job(source="https://youtube.com/watch?v=sample", status="done")
        db.add(job)
        db.flush()

        # Insert a clip pointing to an illegal system file
        bad_clip = Clip(
            job_id=job.id,
            clip_id="bad",
            video_path="C:\\Windows\\win.ini",
        )
        db.add(bad_clip)
        db.commit()
        bad_clip_id = bad_clip.id

    res = client.get(f"/api/v1/clips/{bad_clip_id}/download")
    assert res.status_code == 403
    assert "Access denied" in res.json()["detail"]
