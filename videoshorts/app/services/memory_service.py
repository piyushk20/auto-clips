"""
memory_service.py — Mem0 AI Memory layer integration for VideoShorts.

Maintains personalized, long-term memory across sessions using Mem0,
powered by Google Gemini LLM and Gemini Embeddings stored in a local Qdrant vector store.
"""
from __future__ import annotations

import logging
import os
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.config import settings

log = logging.getLogger(__name__)

# Default user identifier for single-user studio desktop deployment
DEFAULT_USER_ID = "default_creator"

DEFAULT_SEED_MEMORIES = [
    "Always generate all video clip titles, reasons, and descriptions in fluent, engaging English.",
    "Prioritize short video hooks in the first 3 to 5 seconds to maximize viewer retention on YouTube Shorts and TikTok.",
    "Target ideal clip duration between 30 and 60 seconds with complete, self-contained thought arcs.",
    "Favor actionable financial, investigative, technical, or philosophical insights with high debate and viral shareability.",
]


class MemoryService:
    """Wrapper around Mem0's Memory engine with lazy initialization and graceful fallbacks."""

    def __init__(self) -> None:
        self._memory = None
        self._lock = threading.Lock()
        self._init_attempted = False

    def _get_memory(self):
        """Lazy-initialize Mem0 Memory instance."""
        if self._memory is not None:
            return self._memory

        with self._lock:
            if self._memory is not None:
                return self._memory

            api_key = settings.get_api_key("gemini")
            if not api_key:
                log.warning("No Gemini API key available; Mem0 memory layer cannot initialize.")
                return None

            try:
                os.environ["MEM0_TELEMETRY"] = "false"
                from mem0 import Memory

                storage_path = os.environ.get("MEM0_STORAGE_PATH")
                if not storage_path:
                    qdrant_dir = settings.outputs_dir / "mem0_qdrant"
                    qdrant_dir.mkdir(parents=True, exist_ok=True)
                    storage_path = str(qdrant_dir.resolve())

                def make_config(q_path: str):
                    return {
                        "vector_store": {
                            "provider": "qdrant",
                            "config": {
                                "collection_name": "videoshorts_memories",
                                "embedding_model_dims": 768,
                                "path": q_path,
                            },
                        },
                        "llm": {
                            "provider": "gemini",
                            "config": {
                                "model": "gemini-3.1-flash-lite",
                                "api_key": api_key,
                            },
                        },
                        "embedder": {
                            "provider": "gemini",
                            "config": {
                                "model": "models/gemini-embedding-001",
                                "embedding_dims": 768,
                                "api_key": api_key,
                            },
                        },
                        "version": "v1.1",
                    }

                try:
                    self._memory = Memory.from_config(make_config(storage_path))
                except Exception as store_err:
                    if "already accessed" in str(store_err).lower() or "locked" in str(store_err).lower():
                        log.warning("Storage path %s is locked by another process. Falling back to in-memory Qdrant instance.", storage_path)
                        self._memory = Memory.from_config(make_config(":memory:"))
                    else:
                        raise

                log.info("Mem0 memory service initialized successfully with Gemini & Qdrant.")

                # Seed initial memories if empty
                if not self._init_attempted:
                    self._init_attempted = True
                    self._ensure_seed_memories()

                return self._memory
            except Exception as exc:
                log.exception("Failed to initialize Mem0 memory service: %s", exc)
                return None

    def _ensure_seed_memories(self) -> None:
        """Seed starter creator rules if none exist."""
        try:
            existing = self.get_memories(user_id=DEFAULT_USER_ID)
            if not existing:
                log.info("Seeding initial VideoShorts creator preferences into Mem0...")
                for seed in DEFAULT_SEED_MEMORIES:
                    self.add_memory(seed, user_id=DEFAULT_USER_ID, metadata={"system_seed": True})
        except Exception as seed_err:
            log.warning("Could not seed default memories: %s", seed_err)

    def add_memory(
        self,
        text: str,
        user_id: str = DEFAULT_USER_ID,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Store a new preference, guideline, or creator memory."""
        m = self._get_memory()
        if not m:
            return {"error": "Memory service unavailable (check GEMINI_API_KEY).", "results": []}

        try:
            res = m.add(text, user_id=user_id, metadata=metadata or {})
            log.info("Mem0 added memory: %s", res)
            return res if isinstance(res, dict) else {"results": res}
        except Exception as exc:
            log.error("Failed to add memory to Mem0: %s", exc)
            return {"error": str(exc), "results": []}

    def get_memories(self, user_id: str = DEFAULT_USER_ID) -> List[Dict[str, Any]]:
        """Retrieve all stored memories for a user."""
        m = self._get_memory()
        if not m:
            return []

        try:
            res = m.get_all(filters={"user_id": user_id})
            if isinstance(res, dict):
                return res.get("results", [])
            elif isinstance(res, list):
                return res
            return []
        except Exception as exc:
            log.error("Failed to retrieve memories from Mem0: %s", exc)
            return []

    def search_memories(
        self,
        query: str,
        user_id: str = DEFAULT_USER_ID,
        limit: int = 5,
    ) -> List[Dict[str, Any]]:
        """Semantically search memories relevant to a query."""
        m = self._get_memory()
        if not m:
            return []

        try:
            res = m.search(query=query, filters={"user_id": user_id}, limit=limit)
            if isinstance(res, dict):
                return res.get("results", [])
            elif isinstance(res, list):
                return res
            return []
        except Exception as exc:
            log.error("Failed to search memories in Mem0: %s", exc)
            return []

    def delete_memory(self, memory_id: str) -> bool:
        """Delete a memory item by ID."""
        m = self._get_memory()
        if not m:
            return False

        try:
            m.delete(memory_id=memory_id)
            log.info("Deleted memory %s from Mem0", memory_id)
            return True
        except Exception as exc:
            log.error("Failed to delete memory %s: %s", memory_id, exc)
            return False

    def get_prompt_context(self, user_id: str = DEFAULT_USER_ID, max_items: int = 6) -> str:
        """
        Compile active creator memories into an instruction block to inject into AI prompts.
        """
        memories = self.get_memories(user_id=user_id)
        if not memories:
            return ""

        lines = []
        for item in memories[:max_items]:
            mem_text = item.get("memory") or item.get("content")
            if mem_text:
                lines.append(f"- {mem_text.strip()}")

        if not lines:
            return ""

        return (
            "【CREATOR PREFERENCES & MEMORY (via Mem0)】:\n"
            + "\n".join(lines)
            + "\nAlways adhere strictly to these creator rules and style guidelines.\n"
        )


# Global singleton instance
memory_service = MemoryService()
