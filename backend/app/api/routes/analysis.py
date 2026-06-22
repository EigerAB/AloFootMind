"""Pre-match, SSE task stream, and chat endpoints."""
import asyncio
import json
import uuid
from typing import AsyncGenerator

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.graph import run_analysis
from app.agents.state import AnalysisState
from app.agents.subgraphs.qa import (
    build_qa_graph,
    stream_answer,
    stream_direct_answer,
    stream_boundary_answer,
)
import logging

from app.core.config import settings
from app.core.security import get_current_user, require_role
from app.db.models import User
from app.db.postgres import get_db
from app.db.redis_client import get_redis

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["analysis"])


class PreMatchRequest(BaseModel):
    home_team_id: int
    away_team_id: int
    language: str = "en"


class ChatRequest(BaseModel):
    query: str
    session_id: int | None = None
    conversation_history: list[dict] | None = None
    qa_meta: dict | None = None  # football_intent_count, generic_turn_count


class ChatStreamRequest(BaseModel):
    query: str
    session_id: int | None = None
    conversation_history: list[dict] | None = None
    qa_meta: dict | None = None
    rag_context: list[dict] | None = None
    step_log: list[dict] | None = None
    route: str = "classify"


class CreateSessionRequest(BaseModel):
    name: str | None = None
    initial_message: str | None = None


class RenameSessionRequest(BaseModel):
    name: str


class CancelSessionRequest(BaseModel):
    messages: list[dict] | None = None


async def _template_user_id(db: AsyncSession) -> int | None:
    from sqlalchemy import select as _select
    result = await db.execute(_select(User).where(User.email == settings.GUEST_TEMPLATE_EMAIL))
    u = result.scalar_one_or_none()
    return u.id if u else None


@router.post("/pre-match")
async def trigger_pre_match(
    body: PreMatchRequest,
    background_tasks: BackgroundTasks,
    user: User = Depends(require_role("full")),
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
            "user_id": user.id,
        },
    )
    return {"task_id": task_id, "status": "pending"}


@router.get("/pre-match/reports")
async def list_pre_match_reports(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    effective_uid = user.id
    if user.role == "guest":
        effective_uid = await _template_user_id(session)
        if effective_uid is None:
            return []
    result = await session.execute(
        text("""
            SELECT ar.id, ar.home_team_id, ar.away_team_id, ar.report_markdown,
                   ar.created_at, ht.team_name AS home_team_name, at.team_name AS away_team_name
            FROM analysis_reports ar
            JOIN teams ht ON ar.home_team_id = ht.team_id
            JOIN teams at ON ar.away_team_id = at.team_id
            WHERE ar.user_id = :uid AND ar.report_type = 'pre_match'
            ORDER BY ar.created_at DESC
            LIMIT 5
        """),
        {"uid": effective_uid},
    )
    rows = result.mappings().all()
    return [
        {
            "id": r["id"],
            "home_team_id": r["home_team_id"],
            "away_team_id": r["away_team_id"],
            "home_team_name": r["home_team_name"],
            "away_team_name": r["away_team_name"],
            "report_markdown": r["report_markdown"],
            "created_at": str(r["created_at"]),
        }
        for r in rows
    ]


@router.delete("/pre-match/reports/{report_id}")
async def delete_pre_match_report(
    report_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    result = await session.execute(
        text("DELETE FROM analysis_reports WHERE id = :rid AND user_id = :uid AND report_type = 'pre_match' RETURNING id"),
        {"rid": report_id, "uid": user.id},
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Report not found")
    await session.commit()
    return {"message": "Deleted"}


@router.delete("/pre-match/reports")
async def clear_pre_match_reports(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    await session.execute(
        text("DELETE FROM analysis_reports WHERE user_id = :uid AND report_type = 'pre_match'"),
        {"uid": user.id},
    )
    await session.commit()
    return {"message": "All cleared"}


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


async def _check_session_limit(db: AsyncSession, user_id: int, limit: int = 10) -> None:
    result = await db.execute(
        text("SELECT COUNT(*) FROM chat_sessions WHERE user_id = :uid"),
        {"uid": user_id},
    )
    count = result.scalar_one()
    if count >= limit:
        raise HTTPException(
            status_code=429,
            detail=f"SESSION_LIMIT_REACHED:{limit}",
        )


@router.post("/chat")
async def chat(
    body: ChatRequest,
    user: User = Depends(require_role("trial", "full")),
    db: AsyncSession = Depends(get_db),
):
    """Streaming chat endpoint — uses qa_graph for routing + stream_answer for SSE."""
    query = body.query.strip()
    if not query:
        raise HTTPException(status_code=400, detail="Query cannot be empty")

    session_id = body.session_id
    history: list[dict] = []
    qa_meta = {"football_intent_count": 0, "generic_turn_count": 0}

    if session_id:
        result = await db.execute(
            text("SELECT id, messages, qa_meta FROM chat_sessions WHERE id = :sid AND user_id = :uid"),
            {"sid": session_id, "uid": user.id},
        )
        row = result.mappings().first()
        if row:
            history = list(row["messages"])
            qa_meta = dict(row["qa_meta"])
        else:
            raise HTTPException(status_code=404, detail="Session not found")

    if not history and body.conversation_history:
        history = list(body.conversation_history)

    if body.qa_meta:
        qa_meta = body.qa_meta

    # Append user message
    history.append({"role": "user", "content": query})

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
        "user_id": user.id,
    }

    graph = build_qa_graph()
    try:
        result = await asyncio.wait_for(graph.ainvoke(state), timeout=30.0)
        ar = result.get("analysis_result", {})
        route = ar.get("_route", "classify")
        updated_qa_meta = ar.get("qa_meta", qa_meta)
    except asyncio.TimeoutError:
        logger.warning("[chat] graph.ainvoke timed out for query: %s", query[:80])
        result = {}
        route = "classify"
        updated_qa_meta = qa_meta

    session_id_holder = [session_id]

    async def _generate():
        full_response = ""
        sources = []
        try:
            # Emit agent step_log entries before token stream so frontend can show Thinking panel
            for entry in result.get("step_log", []):
                yield f"event: step\ndata: {json.dumps(entry, ensure_ascii=False, default=str)}\n\n"
                await asyncio.sleep(0)

            if route == "classify":
                rag_context = result.get("rag_context", [])
                async for token in stream_answer(query, rag_context, history, language="zh"):
                    full_response += token
                    yield f"data: {json.dumps({'token': token}, ensure_ascii=False)}\n\n"

                sources = [
                    {"text": r["text"], "collection": r.get("collection", ""), "score": r.get("score", 0)}
                    for r in rag_context[:5]
                ]
            elif route == "direct_answer":
                async for token in stream_direct_answer(query, history, language="zh"):
                    full_response += token
                    yield f"data: {json.dumps({'token': token}, ensure_ascii=False)}\n\n"
            else:
                async for token in stream_boundary_answer(query, history, language="zh"):
                    full_response += token
                    yield f"data: {json.dumps({'token': token}, ensure_ascii=False)}\n\n"

            # Save session
            from app.db.postgres import AsyncSessionLocal
            async with AsyncSessionLocal() as save_db:
                new_messages = history + [{"role": "assistant", "content": full_response, "sources": sources}]
                if session_id_holder[0]:
                    await save_db.execute(
                        text("""
                            UPDATE chat_sessions
                            SET messages = :msgs, qa_meta = :qam, updated_at = NOW()
                            WHERE id = :sid AND user_id = :uid
                        """),
                        {
                            "msgs": json.dumps(new_messages, ensure_ascii=False),
                            "qam": json.dumps(updated_qa_meta, ensure_ascii=False),
                            "sid": session_id_holder[0],
                            "uid": user.id,
                        },
                    )
                else:
                    res = await save_db.execute(
                        text("""
                            INSERT INTO chat_sessions (user_id, name, messages, qa_meta)
                            VALUES (:uid, :name, :msgs, :qam)
                            RETURNING id
                        """),
                        {
                            "uid": user.id,
                            "name": query[:30],
                            "msgs": json.dumps(new_messages, ensure_ascii=False),
                            "qam": json.dumps(updated_qa_meta, ensure_ascii=False),
                        },
                    )
                    new_id = res.scalar_one()
                    session_id_holder[0] = new_id

                await save_db.commit()

            yield (
                f"event: done\n"
                f"data: {json.dumps({'sources': sources, 'qa_meta': updated_qa_meta, 'session_id': session_id_holder[0]}, ensure_ascii=False)}\n\n"
            )
        except GeneratorExit:
            # Client disconnected (abort) — don't save partial response
            raise
        except Exception as e:
            yield (
                f"event: error\n"
                f"data: {json.dumps({'error': str(e)}, ensure_ascii=False)}\n\n"
            )

    return StreamingResponse(
        _generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/chat/plan")
async def chat_plan(
    body: ChatRequest,
    user: User = Depends(require_role("trial", "full")),
    db: AsyncSession = Depends(get_db),
):
    """Sync endpoint: run the QA graph (query → rewrite → classify → rag_plan → rag_retrieval).
    Returns step_log, rag_context, and analysis_result.  No LLM answer generation."""
    query = body.query.strip()
    if not query:
        raise HTTPException(status_code=400, detail="Query cannot be empty")

    session_id = body.session_id
    history: list[dict] = []
    qa_meta = {"football_intent_count": 0, "generic_turn_count": 0}

    if session_id:
        result = await db.execute(
            text("SELECT id, messages, qa_meta FROM chat_sessions WHERE id = :sid AND user_id = :uid"),
            {"sid": session_id, "uid": user.id},
        )
        row = result.mappings().first()
        if row:
            history = list(row["messages"])
            qa_meta = dict(row["qa_meta"])
        else:
            raise HTTPException(status_code=404, detail="Session not found")

    if not history and body.conversation_history:
        history = list(body.conversation_history)

    if body.qa_meta:
        qa_meta = body.qa_meta

    history.append({"role": "user", "content": query})

    state: AnalysisState = {
        "task_id": f"chat-plan-{uuid.uuid4().hex[:8]}",
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
        "user_id": user.id,
    }

    graph = build_qa_graph()
    try:
        result = await asyncio.wait_for(graph.ainvoke(state), timeout=30.0)
    except asyncio.TimeoutError:
        logger.warning("[chat_plan] graph.ainvoke timed out for query: %s", query[:80])
        result = {}

    ar = result.get("analysis_result", {})
    updated_qa_meta = ar.get("qa_meta", qa_meta)

    # We do NOT save session here — /chat/stream will do it.
    return {
        "step_log": result.get("step_log", []),
        "rag_context": [
            {"text": r["text"], "collection": r.get("collection", ""), "score": r.get("score", 0)}
            for r in result.get("rag_context", [])
        ],
        "analysis_result": {
            "_route": ar.get("_route", "classify"),
            "rewritten_query": ar.get("rewritten_query", ""),
            "query_levels": ar.get("query_levels", []),
            "rag_plan": ar.get("rag_plan", []),
            "qa_meta": updated_qa_meta,
        },
        "session_id": session_id,
    }


@router.post("/chat/plan/stream")
async def chat_plan_stream(
    body: ChatRequest,
    user: User = Depends(require_role("trial", "full")),
    db: AsyncSession = Depends(get_db),
):
    """SSE endpoint: run QA graph and stream step events as each node completes.
    Emits 'event: step' for each completed step, then 'event: done' with full plan result."""
    query = body.query.strip()
    if not query:
        raise HTTPException(status_code=400, detail="Query cannot be empty")

    session_id = body.session_id
    history: list[dict] = []
    qa_meta = {"football_intent_count": 0, "generic_turn_count": 0}

    if session_id:
        result = await db.execute(
            text("SELECT id, messages, qa_meta FROM chat_sessions WHERE id = :sid AND user_id = :uid"),
            {"sid": session_id, "uid": user.id},
        )
        row = result.mappings().first()
        if row:
            history = list(row["messages"])
            qa_meta = dict(row["qa_meta"])
        else:
            raise HTTPException(status_code=404, detail="Session not found")

    if not history and body.conversation_history:
        history = list(body.conversation_history)

    if body.qa_meta:
        qa_meta = body.qa_meta

    history.append({"role": "user", "content": query})

    state: AnalysisState = {
        "task_id": f"chat-plan-{uuid.uuid4().hex[:8]}",
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
        "user_id": user.id,
    }

    async def _generate() -> AsyncGenerator[str, None]:
        graph = build_qa_graph()
        accumulated_steps: list[dict] = []
        final_result: dict = {}

        try:
            async with asyncio.timeout(30.0):
                async for chunk in graph.astream(state, stream_mode="updates"):
                    for node_name, node_output in chunk.items():
                        new_steps = node_output.get("step_log", [])
                        for step in new_steps:
                            if step not in accumulated_steps:
                                accumulated_steps.append(step)
                                yield (
                                    f"event: step\n"
                                    f"data: {json.dumps(step, ensure_ascii=False)}\n\n"
                                )
                        # Merge node output into final_result
                        for k, v in node_output.items():
                            if k == "step_log":
                                continue
                            if k == "analysis_result" and isinstance(v, dict):
                                existing = final_result.get("analysis_result", {})
                                final_result["analysis_result"] = {**existing, **v}
                            elif k == "rag_context" and v:
                                final_result["rag_context"] = v
                            else:
                                final_result[k] = v

        except (asyncio.TimeoutError, TimeoutError):
            logger.warning("[chat_plan_stream] graph timed out for query: %s", query[:80])

        ar = final_result.get("analysis_result", {})
        updated_qa_meta = ar.get("qa_meta", qa_meta)

        done_payload = {
            "step_log": accumulated_steps,
            "rag_context": [
                {"text": r["text"], "collection": r.get("collection", ""), "score": r.get("score", 0)}
                for r in final_result.get("rag_context", [])
            ],
            "analysis_result": {
                "_route": ar.get("_route", "classify"),
                "rewritten_query": ar.get("rewritten_query", ""),
                "query_levels": ar.get("query_levels", []),
                "rag_plan": ar.get("rag_plan", []),
                "qa_meta": updated_qa_meta,
            },
            "session_id": session_id,
        }
        yield (
            f"event: done\n"
            f"data: {json.dumps(done_payload, ensure_ascii=False)}\n\n"
        )

    return StreamingResponse(
        _generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/chat/stream")
async def chat_stream(
    body: ChatStreamRequest,
    user: User = Depends(require_role("trial", "full")),
    db: AsyncSession = Depends(get_db),
):
    """SSE endpoint: stream LLM answer only.  Expects rag_context and route from /chat/plan."""
    query = body.query.strip()
    if not query:
        raise HTTPException(status_code=400, detail="Query cannot be empty")

    session_id = body.session_id
    history: list[dict] = []
    qa_meta = {"football_intent_count": 0, "generic_turn_count": 0}

    if session_id:
        result = await db.execute(
            text("SELECT id, messages, qa_meta FROM chat_sessions WHERE id = :sid AND user_id = :uid"),
            {"sid": session_id, "uid": user.id},
        )
        row = result.mappings().first()
        if row:
            history = list(row["messages"])
            qa_meta = dict(row["qa_meta"])
        else:
            raise HTTPException(status_code=404, detail="Session not found")

    if not history and body.conversation_history:
        history = list(body.conversation_history)

    if body.qa_meta:
        qa_meta = body.qa_meta

    history.append({"role": "user", "content": query})

    route = body.route or "classify"
    rag_context = body.rag_context or []
    updated_qa_meta = body.qa_meta or qa_meta
    session_id_holder = [session_id]

    async def _generate():
        full_response = ""
        sources = [
            {"text": r["text"], "collection": r.get("collection", ""), "score": r.get("score", 0)}
            for r in rag_context[:5]
        ]
        try:
            if route == "classify":
                async for token in stream_answer(query, rag_context, history, language="zh"):
                    full_response += token
                    yield f"data: {json.dumps({'token': token}, ensure_ascii=False)}\n\n"
            elif route == "direct_answer":
                async for token in stream_direct_answer(query, history, language="zh"):
                    full_response += token
                    yield f"data: {json.dumps({'token': token}, ensure_ascii=False)}\n\n"
            else:
                async for token in stream_boundary_answer(query, history, language="zh"):
                    full_response += token
                    yield f"data: {json.dumps({'token': token}, ensure_ascii=False)}\n\n"

            # Save session
            from app.db.postgres import AsyncSessionLocal
            async with AsyncSessionLocal() as save_db:
                assistant_msg = {
                    "role": "assistant",
                    "content": full_response,
                    "thinking": {
                        "steps": body.step_log or [],
                        "rag_context": rag_context,
                    },
                }
                new_messages = history + [assistant_msg]
                if session_id_holder[0]:
                    await save_db.execute(
                        text("""
                            UPDATE chat_sessions
                            SET messages = :msgs, qa_meta = :qam, updated_at = NOW()
                            WHERE id = :sid AND user_id = :uid
                        """),
                        {
                            "msgs": json.dumps(new_messages, ensure_ascii=False),
                            "qam": json.dumps(updated_qa_meta, ensure_ascii=False),
                            "sid": session_id_holder[0],
                            "uid": user.id,
                        },
                    )
                else:
                    res = await save_db.execute(
                        text("""
                            INSERT INTO chat_sessions (user_id, name, messages, qa_meta)
                            VALUES (:uid, :name, :msgs, :qam)
                            RETURNING id
                        """),
                        {
                            "uid": user.id,
                            "name": query[:30],
                            "msgs": json.dumps(new_messages, ensure_ascii=False),
                            "qam": json.dumps(updated_qa_meta, ensure_ascii=False),
                        },
                    )
                    new_id = res.scalar_one()
                    session_id_holder[0] = new_id
                await save_db.commit()

            yield (
                f"event: done\n"
                f"data: {json.dumps({'sources': sources, 'qa_meta': updated_qa_meta, 'session_id': session_id_holder[0]}, ensure_ascii=False)}\n\n"
            )
        except GeneratorExit:
            raise
        except Exception as e:
            yield (
                f"event: error\n"
                f"data: {json.dumps({'error': str(e)}, ensure_ascii=False)}\n\n"
            )

    return StreamingResponse(
        _generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/chat/sessions")
async def create_chat_session(
    body: CreateSessionRequest,
    user: User = Depends(require_role("trial", "full")),
    db: AsyncSession = Depends(get_db),
):
    await _check_session_limit(db, user.id)
    name = (body.name or "New Chat")[:200]
    initial_msgs = ([{"role": "user", "content": body.initial_message}] if body.initial_message else [])
    result = await db.execute(
        text("""
            INSERT INTO chat_sessions (user_id, name, messages, qa_meta)
            VALUES (:uid, :name, :msgs, :qam)
            RETURNING id
        """),
        {
            "uid": user.id,
            "name": name,
            "msgs": json.dumps(initial_msgs),
            "qam": json.dumps({"football_intent_count": 0, "generic_turn_count": 0}),
        },
    )
    new_id = result.scalar_one()
    await db.commit()
    return {"id": new_id, "name": name}


@router.get("/chat/sessions/{session_id}")
async def get_chat_session(
    session_id: int,
    offset: int = 0,
    limit: int = 0,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    effective_uid = user.id
    if user.role == "guest":
        effective_uid = await _template_user_id(db)
        if effective_uid is None:
            raise HTTPException(status_code=404, detail="Session not found")
    result = await db.execute(
        text("SELECT id, name, messages, qa_meta, updated_at FROM chat_sessions WHERE id = :sid AND user_id = :uid"),
        {"sid": session_id, "uid": effective_uid},
    )
    row = result.mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="Session not found")
    all_msgs: list = list(row["messages"] or [])
    total = len(all_msgs)
    if limit > 0:
        # offset counts from the start of the array; slice [offset : offset+limit]
        page_msgs = all_msgs[offset: offset + limit]
    else:
        page_msgs = all_msgs
    return {
        "id": row["id"],
        "name": row["name"],
        "messages": page_msgs,
        "total": total,
        "qa_meta": row["qa_meta"],
        "updated_at": str(row["updated_at"]),
    }


@router.get("/chat/sessions")
async def list_chat_sessions(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    effective_uid = user.id
    if user.role == "guest":
        effective_uid = await _template_user_id(db)
        if effective_uid is None:
            return []
    result = await db.execute(
        text("""
            SELECT id, name, messages, updated_at
            FROM chat_sessions
            WHERE user_id = :uid
            ORDER BY updated_at DESC
            LIMIT 10
        """),
        {"uid": effective_uid},
    )
    rows = result.mappings().all()
    sessions = []
    for r in rows:
        msgs = r["messages"] or []
        preview = ""
        for m in reversed(msgs):
            if m.get("role") == "assistant":
                preview = m.get("content", "")[:60]
                break
        sessions.append({
            "id": r["id"],
            "name": r["name"],
            "updated_at": str(r["updated_at"]),
            "preview": preview,
        })
    return sessions


@router.patch("/chat/sessions/{session_id}")
async def rename_chat_session(
    session_id: int,
    body: RenameSessionRequest,
    user: User = Depends(require_role("trial", "full")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        text("""
            UPDATE chat_sessions SET name = :name, updated_at = NOW()
            WHERE id = :sid AND user_id = :uid
            RETURNING id
        """),
        {"name": body.name[:200], "sid": session_id, "uid": user.id},
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Session not found")
    await db.commit()
    return {"message": "Renamed"}


@router.post("/chat/sessions/{session_id}/cancel")
async def cancel_chat_session(
    session_id: int,
    body: CancelSessionRequest | None = None,
    user: User = Depends(require_role("trial", "full")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        text("SELECT messages FROM chat_sessions WHERE id = :sid AND user_id = :uid"),
        {"sid": session_id, "uid": user.id},
    )
    row = result.mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="Session not found")
    msgs = list(row["messages"] or [])

    # If frontend sends the latest messages (including the interrupted marker), use them directly
    if body and body.messages:
        msgs = body.messages
    elif msgs and msgs[-1].get("role") == "user":
        msgs.append({"role": "assistant", "content": "__INTERRUPTED__"})

    await db.execute(
        text("UPDATE chat_sessions SET messages = :msgs, updated_at = NOW() WHERE id = :sid AND user_id = :uid"),
        {"msgs": json.dumps(msgs, ensure_ascii=False), "sid": session_id, "uid": user.id},
    )
    await db.commit()
    return {"ok": True}


@router.delete("/chat/sessions/{session_id}")
async def delete_chat_session(
    session_id: int,
    user: User = Depends(require_role("trial", "full")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        text("DELETE FROM chat_sessions WHERE id = :sid AND user_id = :uid RETURNING id"),
        {"sid": session_id, "uid": user.id},
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Session not found")
    await db.commit()
    return {"message": "Deleted"}
