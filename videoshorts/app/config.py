"""
VideoShorts configuration — reads from environment variables only.
No secrets are ever hardcoded here.
"""
from __future__ import annotations

import os
from pathlib import Path


def _load_dotenv() -> None:
    """Load variables from .env file into os.environ if not already set."""
    env_file = Path(__file__).parent.parent / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k = k.strip()
            v = v.strip().strip("'\"")
            if k and k not in os.environ:
                os.environ[k] = v


_load_dotenv()


class Settings:
    # ── AutoClip ──────────────────────────────────────────────────────────
    autoclip_bin: Path = Path(
        os.environ.get(
            "AUTOCLIP_BIN",
            str(Path(__file__).parent.parent.parent / "autoclip-venv" / "Scripts" / "autoclip.exe"),
        )
    )
    autoclip_provider: str = os.environ.get("AUTOCLIP_PROVIDER", "gemini")

    # ── API keys (read-only; never logged) ─────────────────────────────────
    @staticmethod
    def get_api_key(provider: str) -> str | None:
        """Return the API key for *provider*, or None if not set."""
        mapping = {
            "gemini": "GEMINI_API_KEY",
            "openai": "OPENAI_API_KEY",
            "qwen": "QWEN_API_KEY",
            "deepseek": "DEEPSEEK_API_KEY",
        }
        env_var = mapping.get(provider.lower())
        if env_var is None:
            return None
        return os.environ.get(env_var)

    # ── App ────────────────────────────────────────────────────────────────
    database_url: str = os.environ.get("DATABASE_URL", "sqlite:///./videoshorts.db")
    outputs_dir: Path = Path(os.environ.get("OUTPUTS_DIR", "./outputs"))
    host: str = os.environ.get("HOST", "127.0.0.1")
    port: int = int(os.environ.get("PORT", "8000"))
    debug: bool = os.environ.get("DEBUG", "false").lower() == "true"


settings = Settings()
