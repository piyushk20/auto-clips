# VideoShorts — additional workspace rules

## Workflow
- Always read GEMINI.md at the root before modifying any file.
- When modifying engine.py, re-read `.agents/skills/autoclip-engine/SKILL.md` first.
- Run `pytest -m "not slow"` after every change to engine.py or routers.

## No global pip installs
- Use the project venv at `videoshorts/.venv/` for all app dependencies.
- AutoClip venv is at `../autoclip-venv/` — it is separate and read-only from this project's perspective.
