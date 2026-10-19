"""
engine.py — The ONLY module that may call the autoclip CLI via subprocess.

All other modules must import from here. Never call autoclip directly elsewhere.

Exit code contract:
  0  → success  → Result
  1  → pipeline error (bad video, no segments found)  → PipelineError
  2  → environment error (missing ffmpeg, bad API key) → EnvError
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from app.config import settings

log = logging.getLogger(__name__)

# ── Platform constants ─────────────────────────────────────────────────────
SUPPORTED_PLATFORMS: list[str] = [
    "douyin",
    "xiaohongshu",
    "tiktok",
    "instagram_reels",
    "youtube_shorts",
    "youtube_long",
    "bilibili",
]

EXPORT_PRESETS: list[str] = [
    "douyin",
    "xiaohongshu",
    "shorts",
    "bilibili",
    "original",
]

# ── Data types ─────────────────────────────────────────────────────────────


@dataclass
class ClipInfo:
    clip_id: str
    title: str
    score: float
    start_sec: float
    end_sec: float
    duration_sec: float
    reason: str = ""
    file: str | None = None


@dataclass
class Result:
    project_id: str
    clips: list[ClipInfo]
    elapsed_sec: float
    raw: dict = field(default_factory=dict)


@dataclass
class ProduceResult:
    project_id: str
    platform: str
    output_files: list[str]
    raw: dict = field(default_factory=dict)


@dataclass
class ExportResult:
    project_id: str
    preset: str
    zip_path: str | None
    raw: dict = field(default_factory=dict)


class PipelineError(RuntimeError):
    """Exit code 1 — pipeline failed (bad video, no segments, etc.)."""

    def __init__(self, message: str, stderr: str = "") -> None:
        super().__init__(message)
        self.stderr = stderr


class EnvError(RuntimeError):
    """Exit code 2 — environment error (missing ffmpeg, bad API key, etc.)."""

    def __init__(self, message: str, stderr: str = "") -> None:
        super().__init__(message)
        self.stderr = stderr


# ── Internal helpers ───────────────────────────────────────────────────────


def _autoclip_bin() -> Path:
    """Return the path to the autoclip executable, raising EnvError if missing."""
    bin_path = settings.autoclip_bin
    if not bin_path.exists():
        raise EnvError(
            f"autoclip binary not found at {bin_path}. "
            "Set AUTOCLIP_BIN env var or install in the autoclip-venv."
        )
    return bin_path


def _build_env(provider: str = "gemini") -> dict[str, str]:
    """Build subprocess env with API key injected and FFmpeg in PATH."""
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"

    # Ensure system FFmpeg directory is in PATH
    ffmpeg_dir = r"C:\Users\HP\ffmpeg\ffmpeg-2026-04-09-git-d3d0b7a5ee-essentials_build\bin"
    if os.path.isdir(ffmpeg_dir) and ffmpeg_dir not in env.get("PATH", ""):
        env["PATH"] = ffmpeg_dir + os.pathsep + env.get("PATH", "")

    api_key = settings.get_api_key(provider)
    if api_key:
        env["AUTOCLIP_API_KEY"] = api_key
        env["GEMINI_API_KEY"] = api_key
    env["AUTOCLIP_LLM_CONCURRENCY"] = "1"
    autoclip_data = Path.home() / "AppData" / "Roaming" / "AutoClip"
    if autoclip_data.exists():
        env["AUTOCLIP_DATA_DIR"] = str(autoclip_data)
    return env


_active_proc: subprocess.Popen | None = None
_proc_lock = threading.Lock()


def kill_active_process() -> None:
    """Terminate the currently active autoclip/ffmpeg subprocess."""
    global _active_proc
    with _proc_lock:
        if _active_proc and _active_proc.poll() is None:
            try:
                _active_proc.terminate()
                _active_proc.kill()
            except Exception:
                pass
            _active_proc = None


def _run_subprocess(
    cmd: list[str],
    env: dict[str, str],
    progress_cb: Callable[[str], None] | None,
    timeout: int = 3600,
) -> tuple[int, str, str]:
    """
    Run *cmd* as a subprocess, streaming stderr lines to *progress_cb*.
    Returns (returncode, stdout, stderr).
    """
    global _active_proc
    log.debug("Running: %s", " ".join(cmd))
    stdout_lines: list[str] = []
    stderr_lines: list[str] = []

    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            cwd=str(settings.outputs_dir.resolve()),
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        with _proc_lock:
            _active_proc = proc
    except FileNotFoundError as exc:
        raise EnvError(f"autoclip binary not found: {exc}") from exc

    import threading as th

    def _drain_stderr() -> None:
        assert proc.stderr is not None
        for line in proc.stderr:
            line = line.rstrip("\n")
            stderr_lines.append(line)
            if progress_cb:
                try:
                    progress_cb(line)
                except Exception:  # noqa: BLE001
                    pass

    stderr_thread = th.Thread(target=_drain_stderr, daemon=True)
    stderr_thread.start()

    assert proc.stdout is not None
    try:
        for line in proc.stdout:
            stdout_lines.append(line.rstrip("\n"))

        stderr_thread.join(timeout=5)
        proc.wait(timeout=timeout)
    finally:
        with _proc_lock:
            if _active_proc is proc:
                _active_proc = None

    return proc.returncode, "\n".join(stdout_lines), "\n".join(stderr_lines)


def _clean_error_message(msg: str) -> str:
    """Translate known backend/AutoClip Chinese error messages to friendly English."""
    translations = [
        ("视频太短", "Video is too short (under 20 seconds). Please provide a video at least 20 seconds long."),
        ("没有音轨", "Video has no audio track or audible speech."),
        ("字幕路线注定失败", "Cannot process: video has no audible speech or subtitles."),
        ("切片为 0", "No viral segments met the scoring threshold. Try another video or content category."),
        ("没有字幕文件", "No subtitles found and speech transcription could not detect dialogue."),
        ("额度不足", "AI provider API quota or rate limit exceeded."),
        ("配额", "AI provider API quota limit reached."),
        ("API Key 无效", "Invalid AI Provider API Key. Please verify your Gemini API key."),
    ]
    for pattern, eng in translations:
        if pattern in msg:
            return eng
    return msg


def _raise_for_returncode(code: int, stderr: str, stdout: str = "") -> None:
    if code == 0:
        return
    msg = ""
    if stdout:
        try:
            data = json.loads(stdout)
            if isinstance(data, dict) and data.get("error"):
                msg = data["error"]
        except Exception:
            pass
    if not msg:
        msg = (stderr.strip() or stdout.strip())[-500:]

    clean_msg = _clean_error_message(msg)

    if code == 2:
        raise EnvError(f"AutoClip environment error (exit {code}): {clean_msg}", stderr=stderr)
    raise PipelineError(f"AutoClip processing error (exit {code}): {clean_msg}", stderr=stderr)


# ── Public API ─────────────────────────────────────────────────────────────


def slice_video_if_needed(
    video_path: str,
    srt_path: str | None,
    max_duration_sec: float = 600.0,
    progress_cb: Callable[[str], None] | None = None,
) -> tuple[str, str | None]:
    """
    If video exceeds max_duration_sec, slice the first 10 minutes to guarantee
    fast, reliable analysis within LLM API rate limits.
    """
    v_path = Path(video_path)
    ffmpeg_dir = r"C:\Users\HP\ffmpeg\ffmpeg-2026-04-09-git-d3d0b7a5ee-essentials_build\bin"
    ffprobe_bin = str(Path(ffmpeg_dir) / "ffprobe.exe") if (Path(ffmpeg_dir) / "ffprobe.exe").exists() else "ffprobe"
    ffmpeg_bin = str(Path(ffmpeg_dir) / "ffmpeg.exe") if (Path(ffmpeg_dir) / "ffmpeg.exe").exists() else "ffmpeg"
    env = _build_env()

    # Check duration with ffprobe
    probe_cmd = [
        ffprobe_bin, "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", str(v_path),
    ]
    dur = 0.0
    try:
        res = subprocess.run(probe_cmd, capture_output=True, text=True, env=env, timeout=15)
        dur = float(res.stdout.strip())
    except Exception as exc:
        log.warning("ffprobe duration check: %s", exc)

    if dur <= max_duration_sec + 60:
        return video_path, srt_path

    # Need slicing
    out_video = v_path.parent / f"{v_path.stem}_10min.mp4"
    out_srt = (Path(srt_path).parent / f"{Path(srt_path).stem}_10min.srt") if srt_path else None

    if out_video.exists() and out_video.stat().st_size > 100000:
        if progress_cb:
            progress_cb(f"Using cached 10-minute segment for fast AI analysis: {out_video.name}")
        return str(out_video.resolve()), (str(out_srt.resolve()) if out_srt and out_srt.exists() else None)

    if progress_cb:
        progress_cb(f"Video is {int(dur // 60)}m long. Extracting optimal 10-minute segment for AI analysis...")

    # Fast stream copy with ffmpeg
    cut_cmd = [
        ffmpeg_bin, "-y", "-ss", "00:00:00", "-to", "00:10:00",
        "-i", str(v_path), "-c", "copy", str(out_video),
    ]
    subprocess.run(cut_cmd, capture_output=True, env=env, timeout=120)

    # Slice SRT if present
    if srt_path and Path(srt_path).exists():
        try:
            import pysrt
            subs = pysrt.open(srt_path)
            part = subs.slice(ends_before={"minutes": 10})
            part.save(str(out_srt), encoding="utf-8")
        except Exception as exc:
            log.warning("Could not slice SRT: %s", exc)
            out_srt = None

    final_srt = str(out_srt.resolve()) if out_srt and out_srt.exists() else srt_path
    return str(out_video.resolve()), final_srt


def extract_embedded_subtitles(video_path: str) -> str | None:
    """Extract embedded subtitles (e.g. mov_text, srt, ass) from video file if present."""
    v_path = Path(video_path)
    srt_out = v_path.parent / f"{v_path.stem}_embedded.srt"
    if srt_out.exists() and srt_out.stat().st_size > 100:
        return str(srt_out.resolve())

    ffmpeg_dir = r"C:\Users\HP\ffmpeg\ffmpeg-2026-04-09-git-d3d0b7a5ee-essentials_build\bin"
    ffmpeg_bin = str(Path(ffmpeg_dir) / "ffmpeg.exe") if (Path(ffmpeg_dir) / "ffmpeg.exe").exists() else "ffmpeg"

    cmd = [
        ffmpeg_bin, "-y",
        "-i", str(v_path),
        "-map", "0:s:0",
        str(srt_out)
    ]
    try:
        subprocess.run(cmd, capture_output=True, timeout=30)
        if srt_out.exists() and srt_out.stat().st_size > 50:
            return str(srt_out.resolve())
    except Exception:
        pass
    return None


def extract_dialogue_in_range(srt_path: str | None, start_sec: float, end_sec: float) -> list[dict[str, Any]]:
    """
    Extract subtitle dialogue items within [start_sec, end_sec].
    Returns list of {'start': float, 'end': float, 'text': str}.
    """
    if not srt_path or not Path(srt_path).exists():
        return []
    try:
        import pysrt
        subs = pysrt.open(srt_path, encoding="utf-8")
        items: list[dict[str, Any]] = []
        for s in subs:
            s_start = s.start.hours * 3600 + s.start.minutes * 60 + s.start.seconds + s.start.milliseconds / 1000.0
            s_end = s.end.hours * 3600 + s.end.minutes * 60 + s.end.seconds + s.end.milliseconds / 1000.0
            if s_end > start_sec and s_start < end_sec:
                clean_text = " ".join(s.text.replace("\n", " ").split())
                if clean_text:
                    items.append({
                        "start": round(s_start, 2),
                        "end": round(s_end, 2),
                        "text": clean_text,
                    })
        return items
    except Exception as exc:
        log.warning("Could not extract dialogue from SRT: %s", exc)
        return []



def download_source(url: str, progress_cb: Callable[[str], None] | None = None) -> tuple[str, str | None]:
    """
    Download a video URL using yt-dlp to outputs/downloads/.
    Returns (video_path, srt_path).
    """
    import hashlib
    import urllib.request
    import yt_dlp

    downloads_dir = settings.outputs_dir / "downloads"
    downloads_dir.mkdir(parents=True, exist_ok=True)

    url_hash = hashlib.sha256(url.encode("utf-8")).hexdigest()[:10]
    out_template = str(downloads_dir / f"{url_hash}_%(id)s.%(ext)s")

    # Check if video was already downloaded
    existing_videos = list(downloads_dir.glob(f"{url_hash}_*.mp4"))
    if existing_videos and existing_videos[0].stat().st_size > 100000:
        video_path = existing_videos[0]
        srt_candidates = list(downloads_dir.glob(f"{url_hash}_*.srt"))
        srt_path = str(srt_candidates[0].resolve()) if srt_candidates else extract_embedded_subtitles(str(video_path.resolve()))
        if progress_cb:
            progress_cb(f"Found cached video: {video_path.name}" + (f" (with subtitles: {Path(srt_path).name})" if srt_path else ""))
        return slice_video_if_needed(str(video_path.resolve()), srt_path, progress_cb=progress_cb)

    def ydl_hook(d: dict) -> None:
        if progress_cb and d.get("status") == "downloading":
            p = d.get("_percent_str", "").strip()
            spd = d.get("_speed_str", "").strip()
            eta = d.get("_eta_str", "").strip()
            progress_cb(f"Downloading video: {p} at {spd} (ETA {eta})")

    ffmpeg_dir = r"C:\Users\HP\ffmpeg\ffmpeg-2026-04-09-git-d3d0b7a5ee-essentials_build\bin"
    if os.path.isdir(ffmpeg_dir) and ffmpeg_dir not in os.environ.get("PATH", ""):
        os.environ["PATH"] = ffmpeg_dir + os.pathsep + os.environ.get("PATH", "")

    ydl_opts = {
        "ffmpeg_location": ffmpeg_dir,
        "format": "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=1080]+bestaudio/best[height<=1080]/best",
        "merge_output_format": "mp4",
        "outtmpl": out_template,
        "noplaylist": True,
        "progress_hooks": [ydl_hook] if progress_cb else [],
        "quiet": True,
        "no_warnings": True,
        "ignoreerrors": True,
    }

    if progress_cb:
        progress_cb(f"Fetching video from URL: {url}...")

    video_path: Path | None = None
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            if info:
                fn = ydl.prepare_filename(info)
                video_path = Path(fn)
    except Exception as exc:
        log.warning("Primary download encounter: %s", exc)

    if not video_path or not video_path.exists():
        found = list(downloads_dir.glob(f"{url_hash}_*.mp4")) or list(downloads_dir.glob(f"{url_hash}_*.*"))
        valid_found = [f for f in found if f.stat().st_size > 100000]
        if valid_found:
            video_path = valid_found[0]
        elif url.lower().endswith((".mp4", ".mov", ".mkv", ".webm")):
            direct_file = downloads_dir / f"{url_hash}_direct.mp4"
            if progress_cb:
                progress_cb("Direct video URL detected, streaming file download...")
            try:
                urllib.request.urlretrieve(url, str(direct_file))
                if direct_file.exists() and direct_file.stat().st_size > 100000:
                    video_path = direct_file
            except Exception as dl_err:
                log.warning("Direct stream download failed: %s", dl_err)

    if not video_path or not video_path.exists():
        raise PipelineError(f"Failed to download video from URL: {url}. Please ensure the link is publicly accessible.")

    # Optional: attempt to download English subtitles if available (ignore 429 gracefully)
    srt_candidates = list(downloads_dir.glob(f"{url_hash}_*.srt"))
    srt_path = str(srt_candidates[0].resolve()) if srt_candidates else None
    if not srt_path:
        sub_opts = {
            "ffmpeg_location": ffmpeg_dir,
            "skip_download": True,
            "writesubtitles": True,
            "writeautomaticsub": True,
            "subtitlesformat": "srt",
            "subtitleslangs": ["en", "en-US", "en-orig", "en.*", "all"],
            "outtmpl": out_template,
            "noplaylist": True,
            "quiet": True,
            "no_warnings": True,
            "ignoreerrors": True,
        }
        try:
            with yt_dlp.YoutubeDL(sub_opts) as ydl_sub:
                ydl_sub.download([url])
            srt_candidates = list(downloads_dir.glob(f"{url_hash}_*.srt"))
            if srt_candidates:
                srt_path = str(srt_candidates[0].resolve())
        except Exception:
            if progress_cb:
                progress_cb("Subtitles not available or rate-limited on YouTube; AutoClip will transcribe audio via Whisper.")

    if progress_cb:
        msg = f"Video ready: {video_path.name}"
        if srt_path:
            msg += f" (with subtitles: {Path(srt_path).name})"
        else:
            msg += " (audio will be transcribed by AutoClip)"
        progress_cb(msg)

    return slice_video_if_needed(str(video_path.resolve()), srt_path, progress_cb=progress_cb)


def run_job(
    source: str,
    srt: str | None,
    provider: str,
    progress_cb: Callable[[str], None] | None = None,
    category: str = "default",
    min_score: float = 0.72,
) -> Result:
    """
    Analyse *source* (URL or local file path) with AutoClip.

    Returns a Result containing the project_id and scored clip list.
    The caller then calls produce_clips() per platform.

    Raises:
        PipelineError: exit code 1 — bad video, no segments found
        EnvError:      exit code 2 — missing ffmpeg, bad API key
    """
    bin_path = _autoclip_bin()
    env = _build_env(provider)

    VALID_CATEGORIES = {
        "default",
        "knowledge",
        "business",
        "opinion",
        "experience",
        "speech",
        "content_review",
        "entertainment",
    }
    CATEGORY_MAP = {
        "podcast": "experience",
        "education": "knowledge",
        "gaming": "entertainment",
        "comedy": "entertainment",
        "tech": "knowledge",
    }
    if category not in VALID_CATEGORIES:
        category = CATEGORY_MAP.get(category.lower(), "default")

    cmd: list[str] = [
        str(bin_path),
        "run",
        source,
        "--provider", provider,
        "--category", category,
        "--json",
        "--no-db",  # we manage our own DB
    ]
    api_key = settings.get_api_key(provider)
    if api_key:
        cmd += ["--api-key", api_key]
    if provider.lower() == "gemini":
        cmd += ["--model", "gemini-3.1-flash-lite"]
    if srt:
        cmd += ["--srt", srt]
    eff_min_score = min_score if min_score > 0 else 0.72
    cmd += ["--min-score", str(eff_min_score)]

    t0 = time.monotonic()
    code, stdout, stderr = _run_subprocess(cmd, env, progress_cb)
    elapsed = time.monotonic() - t0

    _raise_for_returncode(code, stderr, stdout)

    try:
        raw = json.loads(stdout) if stdout.strip() else {}
    except json.JSONDecodeError as exc:
        raise PipelineError(f"autoclip returned non-JSON stdout: {exc}\n{stdout[:200]}") from exc

    clips = _parse_clips(raw)
    project_id = raw.get("project_id", raw.get("id", ""))

    return Result(
        project_id=project_id,
        clips=clips,
        elapsed_sec=elapsed,
        raw=raw,
    )


def produce_clips(
    source: str,
    platform: str,
    project_name: str | None = None,
    srt: str | None = None,
    portrait_style: str = "auto",
    progress_cb: Callable[[str], None] | None = None,
    timeout: int = 1800,
) -> ProduceResult:
    """
    Render short clips from *source* for *platform*.

    platform must be one of SUPPORTED_PLATFORMS.
    """
    if platform not in SUPPORTED_PLATFORMS:
        raise PipelineError(f"Unsupported platform: {platform!r}. Must be one of {SUPPORTED_PLATFORMS}")

    bin_path = _autoclip_bin()
    env = _build_env()

    cmd: list[str] = [
        str(bin_path),
        "produce",
        source,
        "--platform", platform,
        "--portrait-style", portrait_style,
        "--json",
    ]
    if project_name:
        cmd += ["--name", project_name]
    if srt:
        cmd += ["--srt", srt]

    code, stdout, stderr = _run_subprocess(cmd, env, progress_cb, timeout=timeout)
    _raise_for_returncode(code, stderr)

    try:
        raw = json.loads(stdout) if stdout.strip() else {}
    except json.JSONDecodeError as exc:
        raise PipelineError(f"produce returned non-JSON: {exc}") from exc

    output_files: list[str] = raw.get("output_files", raw.get("files", []))
    project_id: str = raw.get("project_id", raw.get("id", ""))

    return ProduceResult(
        project_id=project_id,
        platform=platform,
        output_files=output_files,
        raw=raw,
    )


def export_clips(
    project_id: str,
    preset: str = "original",
    clip_id: str | None = None,
    progress_cb: Callable[[str], None] | None = None,
) -> ExportResult:
    """
    Export a project's clips to a ZIP bundle.

    preset must be one of EXPORT_PRESETS.
    """
    if preset not in EXPORT_PRESETS:
        raise PipelineError(f"Unsupported preset: {preset!r}. Must be one of {EXPORT_PRESETS}")

    bin_path = _autoclip_bin()
    env = _build_env()

    cmd: list[str] = [
        str(bin_path),
        "export",
        project_id,
        "--preset", preset,
        "--json",
    ]
    if clip_id:
        cmd += ["--clip", clip_id]

    code, stdout, stderr = _run_subprocess(cmd, env, progress_cb)
    _raise_for_returncode(code, stderr)

    try:
        raw = json.loads(stdout) if stdout.strip() else {}
    except json.JSONDecodeError as exc:
        raise PipelineError(f"export returned non-JSON: {exc}") from exc

    zip_path: str | None = raw.get("zip_path") or raw.get("output")

    return ExportResult(
        project_id=project_id,
        preset=preset,
        zip_path=zip_path,
        raw=raw,
    )


def list_outputs(project_id: str) -> dict:
    """Return the outputs metadata for an existing project."""
    bin_path = _autoclip_bin()
    env = _build_env()

    cmd = [str(bin_path), "outputs", project_id]
    code, stdout, stderr = _run_subprocess(cmd, env, None, timeout=60)
    _raise_for_returncode(code, stderr)
    return json.loads(stdout) if stdout.strip() else {}


def check_env() -> dict[str, bool]:
    """Run `autoclip doctor` and return a health dict."""
    try:
        bin_path = _autoclip_bin()
    except EnvError:
        return {"autoclip_bin": False, "ffmpeg": False}

    import shutil
    ffmpeg_dir = r"C:\Users\HP\ffmpeg\ffmpeg-2026-04-09-git-d3d0b7a5ee-essentials_build\bin"
    has_ffmpeg = bool(shutil.which("ffmpeg") or shutil.which("ffmpeg", path=ffmpeg_dir) or shutil.which("ffmpeg", path=env.get("PATH", "")))

    return {
        "autoclip_bin": True,
        "ffmpeg": has_ffmpeg,
    }


# ── Internal parsers ───────────────────────────────────────────────────────


def _parse_timestamp(val: Any) -> float:
    if isinstance(val, (int, float)):
        return float(val)
    if not val or not isinstance(val, str):
        return 0.0
    val = val.strip().replace(",", ".")
    parts = val.split(":")
    try:
        if len(parts) == 3:
            return float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])
        elif len(parts) == 2:
            return float(parts[0]) * 60 + float(parts[1])
        return float(val)
    except Exception:
        return 0.0


def _parse_clips(raw: dict) -> list[ClipInfo]:
    """Parse the clips list from autoclip run --json output."""
    clips_raw = raw.get("clips", raw.get("segments", []))
    result: list[ClipInfo] = []
    for item in clips_raw:
        try:
            start_raw = item.get("start_time") or item.get("start") or item.get("start_sec") or 0.0
            end_raw = item.get("end_time") or item.get("end") or item.get("end_sec") or 0.0
            start_sec = _parse_timestamp(start_raw)
            end_sec = _parse_timestamp(end_raw)
            duration_raw = item.get("duration") or item.get("duration_sec")
            duration_sec = float(duration_raw) if duration_raw is not None else max(0.0, end_sec - start_sec)

            result.append(
                ClipInfo(
                    clip_id=str(item.get("id", item.get("clip_id", ""))),
                    title=item.get("title", item.get("name", "")),
                    score=float(item.get("score", 0.0)),
                    start_sec=start_sec,
                    end_sec=end_sec,
                    duration_sec=duration_sec,
                    reason=item.get("reason", item.get("why", "")),
                    file=item.get("file"),
                )
            )
        except (KeyError, TypeError, ValueError) as exc:
            log.warning("Skipping malformed clip entry: %s — %s", item, exc)
    return result
