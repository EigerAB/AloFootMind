"""Pre-match, SSE task stream, and chat endpoints."""
import asyncio
import json
import uuid
from typing import AsyncGenerator

from fastapi import APIRouter, BackgroundTasks, Depends, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.graph import run_analysis
from app.agents.subgraphs.qa import stream_answer
from app.db.postgres import get_db
from app.db.redis_client import get_redis
from app.services.rag_service import classify_query, retrieve

router = APIRouter(prefix="/api", tags=["analysis"])


class PreMatchRequest(BaseModel):
    home_team_id: int
    away_team_id: int


class ChatRequest(BaseModel):
    query: str
    session_id: str | None = None
    conversation_history: list[dict] | None = None


@router.post("/pre-match")
async def trigger_pre_match(
    body: PreMatchRequest,
    background_tasks: BackgroundTasks,
):
    task_id = str(uuid.uuid4())
    redis = await get_redis()
    await redis.set(f"task:{task_id}:status", "pending", ex=3600)

    background_tasks.add_task(
        run_analysis,
        {
            "task_id": task_id,
            "request_type": "pre_match",
            "team_ids": [body.home_team_id, body.away_team_id],
        },
    )
    return {"task_id": task_id, "status": "pending"}


@router.get("/tasks/{task_id}/status")
async def get_task_status(task_id: str):
    redis = await get_redis()
    status = await redis.get(f"task:{task_id}:status") or "unknown"
    result = await redis.get(f"task:{task_id}:result")
    return {
        "task_id": task_id,
        "status": status,
        "has_result": result is not None,
    }


async def _sse_generator(task_id: str) -> AsyncGenerator[str, None]:
    """Poll Redis step_log and stream incremental SSE events."""
    redis = await get_redis()
    sent_count = 0
    max_wait_seconds = 300
    elapsed = 0
    poll_interval = 0.5

    while elapsed < max_wait_seconds:
        log_raw = await redis.get(f"task:{task_id}:log")
        if log_raw:
            log: list[dict] = json.loads(log_raw)
            new_entries = log[sent_count:]
            for entry in new_entries:
                yield f"data: {json.dumps(entry, ensure_ascii=False)}\n\n"
                sent_count += 1

        status = await redis.get(f"task:{task_id}:status")
        if status == "completed":
            result = await redis.get(f"task:{task_id}:result") or ""
            yield f"event: done\ndata: {json.dumps({'task_id': task_id, 'report_preview': result[:200]}, ensure_ascii=False)}\n\n"
            return
        elif status == "failed":
            yield f"event: error\ndata: {json.dumps({'task_id': task_id, 'error': 'Task failed'})}\n\n"
            return

        await asyncio.sleep(poll_interval)
        elapsed += poll_interval

    yield f"event: error\ndata: {json.dumps({'error': 'Task timed out'})}\n\n"


@router.get("/tasks/{task_id}/stream")
async def stream_task(task_id: str):
    return StreamingResponse(
        _sse_generator(task_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/chat")
async def chat(body: ChatRequest):
    """Streaming chat endpoint — returns SSE token stream."""
    query = body.query.strip()
    if not query:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="Query cannot be empty")

    history = body.conversation_history or []
    levels = classify_query(query)
    rag_context = await retrieve(query=query, top_k=5, force_levels=levels)

    async def _generate():
        async for token in stream_answer(query, rag_context, history):
            yield f"data: {json.dumps({'token': token}, ensure_ascii=False)}\n\n"

        sources = [
            {"text": r["text"][:120], "collection": r["collection"]}
            for r in rag_context[:3]
        ]
        yield f"event: done\ndata: {json.dumps({'sources': sources})}\n\n"

    return StreamingResponse(
        _generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
