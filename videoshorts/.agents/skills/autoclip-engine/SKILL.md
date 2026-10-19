---
name: autoclip-engine
description: >-
  How to call the AutoClip CLI via engine.py. Covers run_job(), Result,
  PipelineError, EnvError, exit codes, progress callbacks, and test patterns.
  Activate when working on engine.py, tests, or any pipeline integration.
---

# AutoClip Engine Adapter — Skill

## Overview

All AutoClip CLI calls are routed through `app/services/engine.py`.
**Never** call `autoclip` directly from any other module.

## Exit Code Contract

| Exit Code | Meaning | Python Exception/Type |
|---|---|---|
| 0 | Success | `Result` dataclass |
| 1 | Pipeline error (bad video, no segments) | `PipelineError` |
| 2 | Environment error (missing ffmpeg, bad API key) | `EnvError` |

## Function Signature

```python
def run_job(
    source: str,                        # URL or absolute path to local video
    srt: str | None,                    # Optional: path to pre-existing .srt
    provider: str,                      # LLM provider: "qwen", "openai", etc.
    platforms: list[str],               # e.g. ["tiktok", "shorts"]
    output_dir: Path,                   # where to write clips/covers/ZIPs
    progress_cb: Callable[[str], None] | None = None,  # receives each stderr line
) -> Result:
    ...
```

## Result Dataclass

```python
@dataclass
class Result:
    job_id: str
    clips: list[ClipInfo]
    elapsed_sec: float
    cost_cny: float | None
```

## CLI Command Built Internally

```
autoclip run \
  --source <source> \
  [--srt <srt>] \
  --provider <provider> \
  --platforms tiktok,shorts \
  --output-dir <output_dir> \
  --json          # single JSON object on stdout when done
```

## Progress Parsing

stderr lines follow this pattern (capture a real run first to verify):
```
[download]  12.3% of 1.20GiB
[transcribe] segment 4/26
[score] scored 10 candidates
[frame] clip 3/10
[render] clip 3/10
[cover] clip 3/10
[copy] clip 3/10
[package] done
```
Parse the bracketed stage name and numeric progress to emit structured events.

## Mock Pattern in Tests

```python
# tests/test_engine.py
from unittest.mock import patch, MagicMock

def test_success(tmp_path):
    fake_result = {"clips": [...], "elapsed_sec": 42.0, "cost_cny": 0.09}
    proc = MagicMock()
    proc.returncode = 0
    proc.stdout.readline.side_effect = [
        json.dumps(fake_result).encode() + b"\n", b""
    ]
    with patch("subprocess.Popen", return_value=proc):
        result = run_job("https://youtube.com/watch?v=test", ...)
    assert len(result.clips) > 0
```

## Integration Test Pattern

```python
@pytest.mark.slow
def test_real_short_video(tmp_path):
    # Uses tests/fixtures/sample_30s.mp4 + tests/fixtures/sample.srt
    result = run_job(
        source=str(Path("tests/fixtures/sample_30s.mp4")),
        srt=str(Path("tests/fixtures/sample.srt")),
        ...
    )
    assert result is not None
```
