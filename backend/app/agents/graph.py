"""Main LangGraph: Supervisor + three Sub-graphs."""
from __future__ import annotations

import uuid
from typing import Literal

from langgraph.graph import END, StateGraph

from app.agents.state import AnalysisState
from app.agents.subgraphs.post_match import build_post_match_graph
from app.agents.subgraphs.pre_match import build_pre_match_graph
from app.agents.subgraphs.qa import build_qa_graph
from app.agents.utils import push_step, set_task_status


_post_match_graph = None
_pre_match_graph = None
_qa_graph = None


def _get_post_match():
    global _post_match_graph
    if _post_match_graph is None:
        _post_match_graph = build_post_match_graph()
    return _post_match_graph


def _get_pre_match():
    global _pre_match_graph
    if _pre_match_graph is None:
        _pre_match_graph = build_pre_match_graph()
    return _pre_match_graph


def _get_qa():
    global _qa_graph
    if _qa_graph is None:
        _qa_graph = build_qa_graph()
    return _qa_graph


async def supervisor_node(state: AnalysisState) -> dict:
    node = "supervisor"
    step_log = await push_step(
        state, node, "started",
        f"Routing task type: {state['request_type']}"
    )
    await set_task_status(state["task_id"], "running")
    step_log = await push_step(state, node, "completed", "Routing to sub-graph.")
    return {"step_log": step_log}


def _route(state: AnalysisState) -> Literal["post_match", "pre_match", "qa"]:
    return state["request_type"]


async def post_match_node(state: AnalysisState) -> dict:
    result = await _get_post_match().ainvoke(state)
    return result


async def pre_match_node(state: AnalysisState) -> dict:
    result = await _get_pre_match().ainvoke(state)
    return result


async def qa_node(state: AnalysisState) -> dict:
    result = await _get_qa().ainvoke(state)
    return result


async def finalize_node(state: AnalysisState) -> dict:
    await set_task_status(state["task_id"], "completed")
    return {}


def build_main_graph():
    graph = StateGraph(AnalysisState)

    graph.add_node("supervisor", supervisor_node)
    graph.add_node("post_match", post_match_node)
    graph.add_node("pre_match", pre_match_node)
    graph.add_node("qa", qa_node)
    graph.add_node("finalize", finalize_node)

    graph.set_entry_point("supervisor")
    graph.add_conditional_edges("supervisor", _route, {
        "post_match": "post_match",
        "pre_match": "pre_match",
        "qa": "qa",
    })
    graph.add_edge("post_match", "finalize")
    graph.add_edge("pre_match", "finalize")
    graph.add_edge("qa", "finalize")
    graph.add_edge("finalize", END)

    return graph.compile()


_main_graph = None


def get_main_graph():
    global _main_graph
    if _main_graph is None:
        _main_graph = build_main_graph()
    return _main_graph


async def run_analysis(initial_state: dict) -> AnalysisState:
    """Entry point for triggering an analysis task."""
    state = AnalysisState(
        task_id=initial_state.get("task_id", str(uuid.uuid4())),
        request_type=initial_state["request_type"],
        match_id=initial_state.get("match_id"),
        team_ids=initial_state.get("team_ids"),
        query=initial_state.get("query"),
        conversation_history=initial_state.get("conversation_history"),
        raw_events=None,
        rag_context=[],
        analysis_result=None,
        report_markdown=None,
        step_log=[],
        error=None,
    )
    return await get_main_graph().ainvoke(state)
