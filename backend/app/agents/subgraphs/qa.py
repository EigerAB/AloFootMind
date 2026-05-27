"""QA Sub-graph: query_classify → rag_retrieval → answer_generation (streaming)."""
from __future__ import annotations

import logging
from typing import AsyncGenerator

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, StateGraph

from app.agents.state import AnalysisState
from app.agents.utils import llm_retry, push_step
from app.core.config import settings
from app.services.rag_service import classify_query, retrieve

logger = logging.getLogger(__name__)

DEEPSEEK_BASE = "https://api.deepseek.com/v1"


def _deepseek_llm(stream: bool = False) -> ChatOpenAI:
    return ChatOpenAI(
        model="deepseek-chat",
        api_key=settings.DEEPSEEK_API_KEY,
        base_url=DEEPSEEK_BASE,
        temperature=0.4,
        max_tokens=1200,
        streaming=stream,
    )


async def query_classify(state: AnalysisState) -> dict:
    node = "query_classify"
    try:
        step_log = await push_step(state, node, "started", "Classifying query intent...")
        query = state.get("query") or ""
        levels = classify_query(query)
        step_log = await push_step(
            state, node, "completed",
            f"Query classified as: {', '.join(levels)}"
        )
        existing = dict(state.get("analysis_result") or {})
        existing["query_levels"] = levels
        return {"step_log": step_log, "analysis_result": existing}

    except Exception as e:
        step_log = await push_step(state, node, "failed", str(e))
        return {"step_log": step_log, "error": str(e)}


async def rag_retrieval(state: AnalysisState) -> dict:
    node = "rag_retrieval"
    try:
        step_log = await push_step(state, node, "started", "Searching knowledge base...")

        ar = state.get("analysis_result") or {}
        levels = ar.get("query_levels", ["tactical_level"])
        query = state.get("query") or ""

        results = await retrieve(
            query=query,
            top_k=5,
            force_levels=levels,
        )

        if not results:
            step_log = await push_step(state, node, "completed", "No matching documents found.")
        else:
            step_log = await push_step(
                state, node, "completed",
                f"Retrieved {len(results)} relevant documents."
            )
        return {"step_log": step_log, "rag_context": results}

    except Exception as e:
        step_log = await push_step(state, node, "failed", str(e))
        return {"step_log": step_log, "rag_context": [], "error": str(e)}


async def answer_generation(state: AnalysisState) -> dict:
    node = "answer_generation"
    try:
        step_log = await push_step(state, node, "started", "Generating answer...")

        query = state.get("query") or ""
        rag_context = state.get("rag_context") or []
        history = state.get("conversation_history") or []

        if rag_context:
            context_text = "\n\n".join(
                f"[Source {i+1}] {r['text']}" for i, r in enumerate(rag_context[:5])
            )
            has_context = True
        else:
            context_text = ""
            has_context = False

        system_prompt = """You are AloFootMind, an expert AI football analyst.
Answer questions based strictly on the provided context from the knowledge base.
If no context is provided, say so honestly — do NOT fabricate football statistics or events.
Format your answers in clear Markdown. Include source citations [Source N] when referencing context."""

        messages: list = [SystemMessage(content=system_prompt)]

        for turn in history[-5:]:
            if turn.get("role") == "user":
                messages.append(HumanMessage(content=turn["content"]))
            elif turn.get("role") == "assistant":
                messages.append(AIMessage(content=turn["content"]))

        user_content = query
        if has_context:
            user_content = f"Context from knowledge base:\n{context_text}\n\nQuestion: {query}"
        else:
            user_content = f"Question: {query}\n\n(No relevant documents found in the knowledge base.)"

        messages.append(HumanMessage(content=user_content))

        llm = _deepseek_llm(stream=False)
        response = await llm.ainvoke(messages)
        answer = response.content

        step_log = await push_step(state, node, "completed", "Answer generated.")
        return {"step_log": step_log, "report_markdown": answer}

    except Exception as e:
        step_log = await push_step(state, node, "failed", str(e))
        return {"step_log": step_log, "error": str(e)}


async def stream_answer(
    query: str,
    rag_context: list[dict],
    conversation_history: list[dict],
) -> AsyncGenerator[str, None]:
    """Stream answer tokens for SSE — used directly by the /api/chat endpoint."""
    if rag_context:
        context_text = "\n\n".join(
            f"[Source {i+1}] {r['text']}" for i, r in enumerate(rag_context[:5])
        )
        user_content = f"Context from knowledge base:\n{context_text}\n\nQuestion: {query}"
    else:
        user_content = f"Question: {query}\n\n(No relevant documents found.)"

    system_prompt = """You are AloFootMind, an expert AI football analyst.
Answer questions based strictly on the provided context. Format in Markdown. Cite [Source N] where applicable."""

    messages: list = [SystemMessage(content=system_prompt)]
    for turn in (conversation_history or [])[-5:]:
        if turn.get("role") == "user":
            messages.append(HumanMessage(content=turn["content"]))
        elif turn.get("role") == "assistant":
            messages.append(AIMessage(content=turn["content"]))
    messages.append(HumanMessage(content=user_content))

    llm = _deepseek_llm(stream=True)
    async for chunk in llm.astream(messages):
        if chunk.content:
            yield chunk.content


def build_qa_graph() -> StateGraph:
    graph = StateGraph(AnalysisState)
    graph.add_node("query_classify", query_classify)
    graph.add_node("rag_retrieval", rag_retrieval)
    graph.add_node("answer_generation", answer_generation)

    graph.set_entry_point("query_classify")
    graph.add_edge("query_classify", "rag_retrieval")
    graph.add_edge("rag_retrieval", "answer_generation")
    graph.add_edge("answer_generation", END)

    return graph.compile()
