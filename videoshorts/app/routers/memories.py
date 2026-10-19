"""
memories.py — Router for querying, adding, and deleting Mem0 AI memories.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.services.memory_service import DEFAULT_USER_ID, memory_service

router = APIRouter(prefix="/api/v1/memories", tags=["memories"])
log = logging.getLogger(__name__)


class CreateMemoryRequest(BaseModel):
    text: str = Field(..., min_length=2, max_length=2000, description="Memory or preference text")
    user_id: Optional[str] = Field(DEFAULT_USER_ID, description="Target user identifier")
    category: Optional[str] = Field(None, description="Optional tag, e.g. style, hook, duration, language")
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict)


@router.get("")
def list_or_search_memories(
    q: Optional[str] = Query(None, description="Optional search query for semantic vector search"),
    user_id: str = Query(DEFAULT_USER_ID, description="Target user identifier"),
    limit: int = Query(20, ge=1, le=100),
) -> dict:
    """
    List all stored memories or perform semantic search if `q` is provided.
    """
    if q and q.strip():
        results = memory_service.search_memories(query=q.strip(), user_id=user_id, limit=limit)
        return {"query": q, "count": len(results), "memories": results}

    results = memory_service.get_memories(user_id=user_id)
    return {"query": None, "count": len(results), "memories": results[:limit]}


@router.post("")
def add_memory(req: CreateMemoryRequest) -> dict:
    """
    Add a new creator rule, style preference, or viral insight to Mem0 memory.
    """
    meta = dict(req.metadata or {})
    if req.category:
        meta["category"] = req.category

    res = memory_service.add_memory(text=req.text.strip(), user_id=req.user_id or DEFAULT_USER_ID, metadata=meta)
    if "error" in res and not res.get("results"):
        raise HTTPException(status_code=500, detail=res["error"])

    return {
        "status": "ok",
        "message": "Memory processed and saved by Mem0",
        "details": res,
    }


@router.delete("/{memory_id}")
def delete_memory(memory_id: str) -> dict:
    """
    Delete a specific memory by its ID.
    """
    success = memory_service.delete_memory(memory_id=memory_id)
    if not success:
        raise HTTPException(status_code=404, detail="Memory not found or could not be deleted")
    return {"status": "ok", "deleted_id": memory_id}


@router.get("/context")
def get_memory_context(user_id: str = Query(DEFAULT_USER_ID)) -> dict:
    """
    Inspect the compiled memory context injected into LLM prompts.
    """
    context = memory_service.get_prompt_context(user_id=user_id)
    memories = memory_service.get_memories(user_id=user_id)
    return {
        "user_id": user_id,
        "count": len(memories),
        "prompt_context": context,
    }
