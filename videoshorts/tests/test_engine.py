"""
test_engine.py — Unit tests for the engine adapter with subprocess mocking.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.services import engine
from app.services.engine import EnvError, PipelineError


def test_platforms_list():
    assert "youtube_shorts" in engine.SUPPORTED_PLATFORMS
    assert "tiktok" in engine.SUPPORTED_PLATFORMS
    assert "instagram_reels" in engine.SUPPORTED_PLATFORMS


def test_produce_clips_unsupported_platform():
    with pytest.raises(PipelineError, match="Unsupported platform"):
        engine.produce_clips("dummy.mp4", "unsupported_platform_xyz")


@patch("app.services.engine._run_subprocess")
@patch("app.services.engine._autoclip_bin")
def test_run_job_success(mock_bin, mock_run):
    mock_bin.return_value = Path("autoclip.exe")
    fake_json = {
        "project_id": "proj_123",
        "clips": [
            {
                "id": "c1",
                "title": "Epic Moment",
                "score": 0.95,
                "start": 10.0,
                "end": 35.0,
                "duration": 25.0,
                "reason": "High emotional spike",
            }
        ],
    }
    mock_run.return_value = (0, json.dumps(fake_json), "Processed successfully\n")

    res = engine.run_job("test_video.mp4", srt=None, provider="gemini")
    assert res.project_id == "proj_123"
    assert len(res.clips) == 1
    assert res.clips[0].title == "Epic Moment"
    assert res.clips[0].score == 0.95
    assert res.clips[0].duration_sec == 25.0


@patch("app.services.engine._run_subprocess")
@patch("app.services.engine._autoclip_bin")
def test_run_job_pipeline_error_exit_1(mock_bin, mock_run):
    mock_bin.return_value = Path("autoclip.exe")
    mock_run.return_value = (1, "", "Error: No viable viral segments found in input video.")

    with pytest.raises(PipelineError) as exc_info:
        engine.run_job("test_video.mp4", srt=None, provider="gemini")
    assert "exit 1" in str(exc_info.value)


@patch("app.services.engine._run_subprocess")
@patch("app.services.engine._autoclip_bin")
def test_run_job_env_error_exit_2(mock_bin, mock_run):
    mock_bin.return_value = Path("autoclip.exe")
    mock_run.return_value = (2, "", "Error: ffmpeg is not installed or not in PATH.")

    with pytest.raises(EnvError) as exc_info:
        engine.run_job("test_video.mp4", srt=None, provider="gemini")
    assert "exit 2" in str(exc_info.value)


@patch("pathlib.Path.exists", return_value=False)
def test_missing_binary_raises_env_error(mock_exists):
    with pytest.raises(EnvError, match="autoclip binary not found"):
        engine._autoclip_bin()
