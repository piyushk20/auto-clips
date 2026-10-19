import sqlite3
from pathlib import Path

db_path = Path(__file__).parent.parent / "videoshorts.db"
conn = sqlite3.connect(db_path)
cur = conn.cursor()

# 1. Delete dummy test clips (e.g. win.ini)
cur.execute("DELETE FROM clips WHERE video_path LIKE '%win.ini%' OR title IS NULL")

# 2. Delete test jobs and failed/cancelled/0-clip jobs
cur.execute("""
DELETE FROM jobs 
WHERE source LIKE '%sample%' 
   OR source LIKE '%dQw4w9WgXcQ%'
   OR id NOT IN (SELECT DISTINCT job_id FROM clips)
""")

conn.commit()

print("Remaining valid jobs with clips in DB:")
rows = cur.execute("""
SELECT j.id, j.status, count(c.id) as clip_cnt, j.source, j.created_at 
FROM jobs j 
JOIN clips c ON j.id = c.job_id 
GROUP BY j.id 
ORDER BY j.created_at DESC
""").fetchall()

for r in rows:
    print(r)

conn.close()
