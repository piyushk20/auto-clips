import re
from pathlib import Path

worker_path = Path("app/services/worker.py")
content = worker_path.read_text(encoding="utf-8")

# 1. Fix payload_clips in _ensure_english_details
old_prompt_block = """    api_key = settings.get_api_key("gemini")
    if not api_key:
        return

    import urllib.request
    from app.services.memory_service import memory_service
    mem_context = memory_service.get_prompt_context()

    prompt = ("""

new_prompt_block = """    api_key = settings.get_api_key("gemini")
    if not api_key:
        return

    import urllib.request
    from app.services.memory_service import memory_service
    mem_context = memory_service.get_prompt_context()

    payload_clips = [{"id": i, "title": c.title, "reason": c.reason} for i, c in enumerate(clips)]

    prompt = ("""

assert old_prompt_block in content, "old_prompt_block not found in worker.py"
content = content.replace(old_prompt_block, new_prompt_block)

# 2. Update source handling to support local uploads and embedded subtitles
old_source_block = """            # 1. Check if source is a web URL and download local video + SRT
            video_file = job_source
            auto_srt = None
            if job_source.startswith("http://") or job_source.startswith("https://"):
                on_progress_line(f"Source is a web URL. Downloading video via yt-dlp...")
                video_file, auto_srt = engine.download_source(job_source, progress_cb=on_progress_line)

            # 2. Run main AutoClip analysis"""

new_source_block = """            # 1. Check if source is a web URL or local uploaded file
            video_file = job_source
            auto_srt = None
            if job_source.startswith("http://") or job_source.startswith("https://"):
                on_progress_line("Source is a web URL. Downloading video via yt-dlp...")
                video_file, auto_srt = engine.download_source(job_source, progress_cb=on_progress_line)
            else:
                on_progress_line(f"Source is a local video file: {Path(job_source).name}")
                embedded_srt = engine.extract_embedded_subtitles(video_file)
                if embedded_srt:
                    auto_srt = embedded_srt
                    on_progress_line(f"Extracted embedded subtitles: {Path(embedded_srt).name}")

            # Ensure any video (uploaded or downloaded) is bounded to 10m to prevent timeouts or 429 quota exhaustion
            video_file, auto_srt = engine.slice_video_if_needed(video_file, auto_srt, progress_cb=on_progress_line)

            # 2. Run main AutoClip analysis"""

assert old_source_block in content, "old_source_block not found in worker.py"
content = content.replace(old_source_block, new_source_block)

# 3. Add direct FFmpeg cut fallback for clips
old_save_block = """                                permanent_video_path = str(dst_p.resolve())
                            except Exception as copy_err:
                                log.warning("Could not copy clip to permanent outputs: %s", copy_err)
                                permanent_video_path = str(src_p.resolve())

                        new_clip = Clip("""

new_save_block = """                                permanent_video_path = str(dst_p.resolve())
                            except Exception as copy_err:
                                log.warning("Could not copy clip to permanent outputs: %s", copy_err)
                                permanent_video_path = str(src_p.resolve())

                        # Direct FFmpeg cut fallback if no produced file was generated
                        if not permanent_video_path or not Path(permanent_video_path).exists():
                            ffmpeg_dir = r"C:\\Users\\HP\\ffmpeg\\ffmpeg-2026-04-09-git-d3d0b7a5ee-essentials_build\\bin"
                            ffmpeg_bin = str(Path(ffmpeg_dir) / "ffmpeg.exe") if (Path(ffmpeg_dir) / "ffmpeg.exe").exists() else "ffmpeg"
                            clean_slug = re.sub(r"[^a-zA-Z0-9]+", "_", clip_info.title or "").strip("_")
                            clean_filename = f"clip_{i+1}_{clean_slug[:45]}.mp4" if clean_slug else f"clip_{i+1}_{clip_info.clip_id}.mp4"
                            dst_p = permanent_clips_dir / clean_filename

                            cut_cmd = [
                                ffmpeg_bin, "-y",
                                "-ss", str(max(0.0, clip_info.start_sec)),
                                "-to", str(clip_info.end_sec),
                                "-i", str(video_file),
                                "-c:v", "libx264", "-c:a", "aac",
                                "-pix_fmt", "yuv420p",
                                str(dst_p)
                            ]
                            try:
                                import subprocess
                                subprocess.run(cut_cmd, capture_output=True, timeout=120)
                                if dst_p.exists() and dst_p.stat().st_size > 1000:
                                    permanent_video_path = str(dst_p.resolve())
                            except Exception as cut_err:
                                log.warning("Direct FFmpeg cut fallback failed for clip %s: %s", clip_info.clip_id, cut_err)

                        new_clip = Clip("""

assert old_save_block in content, "old_save_block not found in worker.py"
content = content.replace(old_save_block, new_save_block)

worker_path.write_text(content, encoding="utf-8")
print("Worker updated successfully!")
