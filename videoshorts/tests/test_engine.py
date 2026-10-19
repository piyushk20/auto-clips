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


def test_extract_dialogue_in_range(tmp_path):
    srt_file = tmp_path / "test.srt"
    srt_content = (
        "1\n00:00:01,000 --> 00:00:05,000\nWelcome to the podcast.\n\n"
        "2\n00:00:06,000 --> 00:00:15,000\nThis is the secret to scaling fast.\n\n"
        "3\n00:00:16,000 --> 00:00:25,000\nMake sure you never cut corners on quality.\n\n"
    )
    srt_file.write_text(srt_content, encoding="utf-8")

    items = engine.extract_dialogue_in_range(str(srt_file), start_sec=5.0, end_sec=20.0)
    assert len(items) == 2
    assert "secret to scaling" in items[0]["text"]
    assert "never cut corners" in items[1]["text"]


def test_refine_and_trim_clips_heuristic():
    from app.services.worker import _refine_and_trim_clips

    long_clip = engine.ClipInfo(
        clip_id="long1",
        title="Uncut Long Segment",
        score=0.88,
        start_sec=10.0,
        end_sec=100.0,
        duration_sec=90.0,
        reason="Good topic but too long",
    )
    clips = [long_clip]
    # No SRT -> runs intelligent heuristic trimming
    _refine_and_trim_clips(clips, srt_path=None, target_max_sec=42.0)

    # Durations should be tightly trimmed (target <= 45s, unwanted intro/outro removed)
    assert clips[0].duration_sec <= 45.0
    assert clips[0].start_sec > 10.0  # wind-up stripped
    assert clips[0].end_sec < 100.0   # trailing chatter stripped

