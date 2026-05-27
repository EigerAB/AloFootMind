"""Shared AnalysisState and step_log utilities."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Annotated, Any, Literal
from typing_extensions import TypedDict

from langgraph.graph.message import add_messages


class StepLogEntry(TypedDict):
    node_name: str
    status: Literal["started", "completed", "failed"]
    summary: str
    timestamp: str


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


def make_step_entry(
    node_name: str,
    status: Literal["started", "completed", "failed"],
    summary: str,
) -> StepLogEntry:
    return StepLogEntry(
        node_name=node_name,
        status=status,
        summary=summary,
        timestamp=_now_iso(),
    )
