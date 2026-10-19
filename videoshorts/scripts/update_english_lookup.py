from pathlib import Path

p = Path("app/services/worker.py")
content = p.read_text(encoding="utf-8")

old_lookup = """                by_id = {it["id"]: it for it in items if "id" in it}
                for i, c in enumerate(clips):
                    if i in by_id:
                        if by_id[i].get("title"):
                            c.title = by_id[i]["title"]
                        if by_id[i].get("reason"):
                            c.reason = by_id[i]["reason"]"""

new_lookup = """                by_id = {}
                for it in items:
                    if "id" in it:
                        by_id[it["id"]] = it
                        by_id[str(it["id"])] = it
                        try:
                            by_id[int(it["id"])] = it
                        except Exception:
                            pass
                for i, c in enumerate(clips):
                    matched = by_id.get(i) or by_id.get(str(i))
                    if matched:
                        if matched.get("title"):
                            c.title = matched["title"]
                        if matched.get("reason"):
                            c.reason = matched["reason"]"""

assert old_lookup in content, "old_lookup not found"
content = content.replace(old_lookup, new_lookup)
p.write_text(content, encoding="utf-8")
print("worker.py English translation lookup updated!")
