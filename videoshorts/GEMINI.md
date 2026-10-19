# VideoShorts — Agent Rules

## Language & Style
- Python 3.10+ with full type annotations on every function and class.
- Use `pathlib.Path` for all file paths; never raw string concatenation.
- Follow PEP 8; max line length 100.
- Docstrings on every public function and class.

## Architecture Guardrails (MANDATORY)
- **Never import AutoClip internals** — interact with it only via CLI subprocess.
- **All engine calls go through `app/services/engine.py`** — no other module may call `autoclip` directly.
- The AutoClip venv lives at `../autoclip-venv/` (outside this repo). Never activate it inside this repo.
- Never edit any file inside the AutoClip venv or AutoClip source.

## Secrets & Security
- **No secrets in files** — API keys, tokens, and passwords live only in environment variables.
- Never `print()` or `log` an API key, token, or secret value.
- Never read `os.environ` for secrets outside of `app/config.py`.
- Never commit `.env` files — they are in `.gitignore`.

## Subprocess Safety
- All `subprocess` calls must specify `cwd`, `env`, and `timeout`.
- Use `shlex.split()` or explicit list args — never shell=True with user input.
- Kill the entire process group on cancel; never leave orphan ffmpeg processes.
- Validate all file paths against the `outputs/` root before passing to subprocess.

## Database
- SQLite via SQLAlchemy; Alembic for migrations.
- Never execute raw SQL strings with f-strings — use parameterized queries.

## Testing
- pytest with `tests/` directory mirroring `app/` layout.
- Mock subprocess in unit tests — never call real `autoclip` CLI in fast tests.
- Integration tests (real CLI) marked `@pytest.mark.slow` — excluded from CI default.

## File Deletion
- Any command that deletes files requires explicit user confirmation first.
- Prefer `outputs/` isolation — never write outside the project folder.

## Commits
- Commit after each phase with a conventional commit message.
- Never commit: `.env`, `outputs/`, `__pycache__/`, `*.pyc`, `autoclip-venv/`.

## VideoShorts — Verified Stable State
- **Workspace**: `c:\Users\HP\Auto-clips\videoshorts`
- **Server Launch**: `& "c:\Users\HP\Auto-clips\videoshorts\.venv\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 6400`
- **Port**: 6400 (FastAPI API + static & dynamic UI + SSE streaming)
- **Health Check**: `http://127.0.0.1:6400/api/v1/health`
- **Dashboard UI**: `http://127.0.0.1:6400/`
- **Test Command**: `& "c:\Users\HP\Auto-clips\videoshorts\.venv\Scripts\pytest.exe" -v` (18/18 tests passing)

