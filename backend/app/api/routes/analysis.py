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
from app.agents.state import AnalysisState
from app.agents.subgraphs.qa import build_qa_graph, stream_answer
from app.db.postgres import get_db
from app.db.redis_client import get_redis

router = APIRouter(prefix="/api", tags=["analysis"])


class PreMatchRequest(BaseModel):
    home_team_id: int
    away_team_id: int
    language: str = "en"


class ChatRequest(BaseModel):
    query: str
    session_id: str | None = None
    conversation_history: list[dict] | None = None
    qa_meta: dict | None = None  # football_intent_count, generic_turn_count


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
            "language": body.language,
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


@router.get("/tasks/{task_id}/result")
async def get_task_result(task_id: str):
    from fastapi import HTTPException
    redis = await get_redis()
    result = await redis.get(f"task:{task_id}:result")
    if result is None:
        raise HTTPException(status_code=404, detail="Result not yet available")
    return {"task_id": task_id, "result": result}


async def _sse_generator(task_id: str) -> AsyncGenerator[str, None]:
    """Poll Redis list and stream incremental SSE events (LRANGE, append-only)."""
    redis = await get_redis()
    sent_count = 0
    max_wait_seconds = 300
    elapsed = 0
    poll_interval = 0.5

    while elapsed < max_wait_seconds:
        new_entries = await redis.lrange(f"task:{task_id}:log", sent_count, -1)
        for raw in new_entries:
            decoded = raw.decode("utf-8") if isinstance(raw, bytes) else raw
            yield f"data: {decoded}\n\n"
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
    """Streaming chat endpoint — uses qa_graph for routing + stream_answer for SSE."""
    query = body.query.strip()
    if not query:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="Query cannot be empty")

    history = body.conversation_history or []
    qa_meta = body.qa_meta or {"football_intent_count": 0, "generic_turn_count": 0}

    # Build state for qa_graph
    state: AnalysisState = {
        "task_id": f"chat-{uuid.uuid4().hex[:8]}",
        "request_type": "qa",
        "match_id": None,
        "team_ids": None,
        "query": query,
        "conversation_history": history,
        "raw_events": None,
        "rag_context": [],
        "analysis_result": {"qa_meta": qa_meta},
        "report_markdown": None,
        "step_log": [],
        "error": None,
        "language": "zh",
    }

    # Run qa_graph to determine route and get context
    graph = build_qa_graph()
    result = await graph.ainvoke(state)

    ar = result.get("analysis_result", {})
    route = ar.get("_route", "classify")
    updated_qa_meta = ar.get("qa_meta", qa_meta)

    async def _generate():
        if route == "classify":
            # Football-related: stream with RAG context
            rag_context = result.get("rag_context", [])
            async for token in stream_answer(query, rag_context, history, language="zh"):
                yield f"data: {json.dumps({'token': token}, ensure_ascii=False)}\n\n"

            sources = [
                {"text": r["text"][:120], "collection": r.get("collection", "")}
                for r in rag_context[:3]
            ]
            yield (
                f"event: done\n"
                f"data: {json.dumps({'sources': sources, 'qa_meta': updated_qa_meta}, ensure_ascii=False)}\n\n"
            )
        else:
            # boundary_answer or direct_answer: pre-generated, yield as single token
            report = result.get("report_markdown", "")
            yield f"data: {json.dumps({'token': report}, ensure_ascii=False)}\n\n"
            yield (
                f"event: done\n"
                f"data: {json.dumps({'sources': [], 'qa_meta': updated_qa_meta}, ensure_ascii=False)}\n\n"
            )

    return StreamingResponse(
        _generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
