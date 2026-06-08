"""Shared AnalysisState and step_log utilities."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Annotated, Any, Literal
from typing_extensions import TypedDict

from langgraph.graph.message import add_messages


class StepLogEntry(TypedDict, total=False):
    node_name: str
    status: Literal["started", "completed", "error"]
    summary: str
    timestamp: str
    data: dict | None


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class AnalysisState(TypedDict):
    task_id: str
    request_type: Literal["post_match", "pre_match", "qa"]
    match_id: int | None
    team_ids: list[int] | None
    query: str | None
    conversation_history: list[dict] | None
    raw_events: list[dict] | None
    rag_context: list[dict]
    analysis_result: dict | None
    report_markdown: str | None
    step_log: list[StepLogEntry]
    error: str | None
    language: str
    user_id: int | None


def make_step_entry(
    node_name: str,
    status: Literal["started", "completed", "error"],
    summary: str,
    data: dict | None = None,
) -> StepLogEntry:
    entry = StepLogEntry(
        node_name=node_name,
        status=status,
        summary=summary,
        timestamp=_now_iso(),
    )
    if data is not None:
        entry["data"] = data
    return entry
