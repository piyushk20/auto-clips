import re
from pathlib import Path

engine_path = Path("app/services/engine.py")
content = engine_path.read_text(encoding="utf-8")

# 1. Update ydl_opts
old_ydl_block = """    ydl_opts = {
        "ffmpeg_location": ffmpeg_dir,
        "format": "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[height<=1080][ext=mp4]/best",
        "outtmpl": out_template,
        "progress_hooks": [ydl_hook] if progress_cb else [],
        "quiet": True,
        "no_warnings": True,
    }"""

new_ydl_block = """    ydl_opts = {
        "ffmpeg_location": ffmpeg_dir,
        "format": "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=1080]+bestaudio/best[height<=1080]/best",
        "merge_output_format": "mp4",
        "outtmpl": out_template,
        "noplaylist": True,
        "progress_hooks": [ydl_hook] if progress_cb else [],
        "quiet": True,
        "no_warnings": True,
        "ignoreerrors": True,
    }"""

assert old_ydl_block in content, "old_ydl_block not found"
content = content.replace(old_ydl_block, new_ydl_block)

# 2. Update video_path check to support .mp4 resolution and direct download fallback
old_check = """    if not video_path or not video_path.exists():
        found = list(downloads_dir.glob(f"{url_hash}_*.mp4")) or list(downloads_dir.glob(f"{url_hash}_*.*"))
        if found and found[0].stat().st_size > 100000:
            video_path = found[0]
        else:
            raise PipelineError(f"Failed to download video from URL: {url}")"""

new_check = """    if not video_path or not video_path.exists():
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
        raise PipelineError(f"Failed to download video from URL: {url}. Please ensure the link is publicly accessible.")"""

assert old_check in content, "old_check not found"
content = content.replace(old_check, new_check)

# 3. Update subtitle languages and fallback
old_sub = """        sub_opts = {
            "ffmpeg_location": ffmpeg_dir,
            "skip_download": True,
            "writesubtitles": True,
            "writeautomaticsub": True,
            "subtitlesformat": "srt",
            "subtitleslangs": ["en", "en-US"],
            "outtmpl": out_template,
            "quiet": True,
            "no_warnings": True,
            "ignoreerrors": True,
        }"""

new_sub = """        sub_opts = {
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
        }"""

assert old_sub in content, "old_sub not found"
content = content.replace(old_sub, new_sub)

# 4. Update eff_min_score in run_job
old_min_score = """    if min_score > 0:
        cmd += ["--min-score", str(min_score)]"""

new_min_score = """    eff_min_score = min_score if min_score > 0 else 0.4
    cmd += ["--min-score", str(eff_min_score)]"""

assert old_min_score in content, "old_min_score not found"
content = content.replace(old_min_score, new_min_score)

engine_path.write_text(content, encoding="utf-8")
print("Engine updated successfully!")
