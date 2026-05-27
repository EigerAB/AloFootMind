"""Agent utility functions: step_log_writer, LLM retry decorator."""
from __future__ import annotations

import asyncio
import functools
import json
import logging
from typing import Any, Callable

from app.agents.state import AnalysisState, StepLogEntry, make_step_entry
from app.db.redis_client import get_redis

logger = logging.getLogger(__name__)

TASK_LOG_TTL = 3600  # 1 hour


async def write_step_log(task_id: str, step_log: list[StepLogEntry]) -> None:
    """Persist current step_log to Redis for SSE consumption."""
    redis = await get_redis()
    key = f"task:{task_id}:log"
    await redis.set(key, json.dumps(step_log, ensure_ascii=False), ex=TASK_LOG_TTL)


async def push_step(
    state: AnalysisState,
    node_name: str,
    status: str,
    summary: str,
) -> list[StepLogEntry]:
    """Append a step entry and sync to Redis. Returns updated log."""
    entry = make_step_entry(node_name, status, summary)
    updated_log = list(state.get("step_log") or []) + [entry]
    await write_step_log(state["task_id"], updated_log)
    return updated_log


async def set_task_status(task_id: str, status: str) -> None:
    redis = await get_redis()
    await redis.set(f"task:{task_id}:status", status, ex=TASK_LOG_TTL)


async def set_task_result(task_id: str, report_markdown: str) -> None:
    redis = await get_redis()
    await redis.set(f"task:{task_id}:result", report_markdown, ex=TASK_LOG_TTL)


def llm_retry(max_retries: int = 3, base_delay: float = 1.0):
    """Decorator: exponential backoff retry for LLM calls."""
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            last_exc: Exception | None = None
            for attempt in range(max_retries):
                try:
                    return await func(*args, **kwargs)
                except Exception as exc:
                    last_exc = exc
                    wait = base_delay * (2 ** attempt)
                    logger.warning(
                        f"[llm_retry] {func.__name__} attempt {attempt+1}/{max_retries} "
                        f"failed: {exc}. Retrying in {wait:.1f}s..."
                    )
                    await asyncio.sleep(wait)
            raise last_exc
        return wrapper
    return decorator
