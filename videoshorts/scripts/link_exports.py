from pathlib import Path
from app.database import SessionLocal
from app.models.job import Clip

exports_dir = Path(r"C:\Users\HP\AppData\Roaming\AutoClip\projects\32e0c0cb-7a60-4543-850f-77f532e3379f\output\exports")

with SessionLocal() as db:
    for f in exports_dir.glob("*_douyin_captions-v2.mp4"):
        cid = f.name.split("_")[0]
        clips = db.query(Clip).filter(Clip.clip_id == cid).all()
        for c in clips:
            c.video_path = str(f.resolve())
            c.platform = "youtube_shorts"
    db.commit()
print("All 7 vertical shorts linked to DB clips!")
