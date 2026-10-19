from app.database import SessionLocal
from app.models.job import Clip

CLIPS_DATA = {
    "1": ("First Whistleblower Debrief: Career Transition & Work Under Pressure", 0.75, 1.44, 69.04, "Reflections on transitioning from high-stakes intelligence reporting to congressional advisory and managing extreme operational pressure."),
    "2": ("Disclosing Sensitive Intel: Congressional Briefings & Coalition Tactics", 0.80, 69.04, 128.16, "Insider roadmap for navigating classified hearings, building bipartisan coalitions, and advancing transparency on sensitive topics."),
    "3": ("The Investigator's Money Trail: Spotting Irregular Programs & Risk", 0.85, 128.16, 183.84, "Forensic breakdown of following irregular financial trails, auditing shadow contracts, and maintaining strict legal guardrails."),
    "4": ("Asset Control & Accountability: Deconstructing Real Misappropriations", 0.82, 183.84, 277.44, "Deep-dive case study analyzing systemic oversight failures, internal audit breakdowns, and government asset recovery."),
    "5": ("Inside Covert Projects: Abuse of Power & Financial Mechanics", 0.75, 275.60, 374.64, "Investigative insights into how long-term legacy projects evade standard audit scrutiny and develop unchecked operational autonomy."),
    "6": ("Iran-Contra Lessons: How Autonomous Units Fund Themselves", 0.80, 374.64, 495.84, "Historical analysis connecting modern oversight gaps with classic historical precedents of off-the-books financing networks."),
    "7": ("Intelligence Officer Survival Guide: Protected Disclosures & Safety", 0.85, 495.84, 599.52, "Essential counsel from veteran intelligence personnel on legal whistleblower mechanisms, career preservation, and psychological resilience."),
}

with SessionLocal() as db:
    for cid, (title, score, s_sec, e_sec, reason) in CLIPS_DATA.items():
        clips = db.query(Clip).filter(Clip.clip_id == cid).all()
        for c in clips:
            c.title = title
            c.score = score
            c.start_sec = s_sec
            c.end_sec = e_sec
            c.duration_sec = e_sec - s_sec
            c.reason = reason
    db.commit()
print("Successfully updated clip titles and metadata")
