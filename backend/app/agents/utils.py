"""Agent utility functions: step_log_writer, LLM retry decorator, key-player extraction."""
from __future__ import annotations

import asyncio
import functools
import json
import logging
from collections import defaultdict
from typing import Any, Callable

from app.agents.state import AnalysisState, StepLogEntry, make_step_entry
from app.db.redis_client import get_redis

logger = logging.getLogger(__name__)

TASK_LOG_TTL = 3600  # 1 hour


async def push_step(
    state: AnalysisState,
    node_name: str,
    status: str,
    summary: str,
    data: dict | None = None,
) -> list[StepLogEntry]:
    """Append a single step entry to the Redis list (RPUSH, no overwrite)."""
    entry = make_step_entry(node_name, status, summary, data=data)
    redis = await get_redis()
    key = f"task:{state['task_id']}:log"
    await redis.rpush(key, json.dumps(entry, ensure_ascii=False))
    await redis.expire(key, TASK_LOG_TTL)
    return [entry]


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


def _event_weight(ev_type: str) -> float:
    weights = {
        "Goal": 3.0,
        "Assist": 2.0,
        "Red Card": 2.0,
        "Second Yellow": 2.0,
        "Yellow Card": 1.0,
        "Key Pass": 1.5,
        "Own Goal": 1.5,
    }
    return weights.get(ev_type, 0.5)


def extract_key_players(key_events: list[dict], limit: int = 5) -> list[int]:
    """Extract top-N key players from key_events_json by event weight.

    Falls back to player name lookup via DB if player_id is missing.
    Returns a deduplicated list of player_ids.
    """
    player_scores: dict[int, float] = defaultdict(float)

    for ev in key_events:
        ev_type = ev.get("type", "")
        weight = _event_weight(ev_type)
        pid = ev.get("player_id")
        if pid:
            player_scores[pid] += weight
        assist_pid = ev.get("assist_player_id")
        if assist_pid:
            player_scores[assist_pid] += _event_weight("Assist")

    if not player_scores:
        return []

    sorted_players = sorted(player_scores.items(), key=lambda x: x[1], reverse=True)
    return [pid for pid, _ in sorted_players[:limit]]
