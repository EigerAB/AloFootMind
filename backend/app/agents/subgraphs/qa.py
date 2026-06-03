"""QA Sub-graph: query_classify → rag_retrieval → answer_generation (streaming)."""
from __future__ import annotations

import logging
import re
from typing import AsyncGenerator

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, StateGraph
from sqlalchemy import text

from app.agents.state import AnalysisState
from app.agents.utils import llm_retry, push_step
from app.core.config import settings
from app.db.postgres import AsyncSessionLocal
from app.services.rag_service import classify_query, retrieve

logger = logging.getLogger(__name__)

DEEPSEEK_BASE = "https://api.deepseek.com/v1"

# ─────────────────────────────────────────────
#  Entity Dictionary (teams + players from DB)
# ─────────────────────────────────────────────
_ENTITY_DICT: dict[str, dict] = {}
# e.g. {"勒沃库森": {"id": 904, "type": "team"}, ...}


async def _load_entity_dictionary() -> dict[str, dict]:
    """Load team & player names from PostgreSQL into memory cache."""
    global _ENTITY_DICT
    if _ENTITY_DICT:
        return _ENTITY_DICT

    async with AsyncSessionLocal() as session:
        # Teams (Chinese names)
        team_result = await session.execute(text("SELECT team_id, team_name FROM teams"))
        for row in team_result.mappings():
            name = row["team_name"]
            if name:
                _ENTITY_DICT[name] = {"id": row["team_id"], "type": "team"}

        # Players (English names from DB)
        player_result = await session.execute(text("SELECT player_id, player_name FROM players"))
        for row in player_result.mappings():
            name = row["player_name"]
            if name:
                _ENTITY_DICT[name] = {"id": row["player_id"], "type": "player"}

    logger.info("Loaded %d entities into QA dictionary", len(_ENTITY_DICT))
    return _ENTITY_DICT


def _match_entities(query: str) -> list[dict]:
    """Fuzzy match entities in query against the cached dictionary.
    Returns list of matched entity dicts.
    """
    if not _ENTITY_DICT:
        return []

    found: list[dict] = []
    seen_ids: set[int] = set()

    # Try exact and substring match (longest first to avoid partial matches)
    sorted_names = sorted(_ENTITY_DICT.keys(), key=len, reverse=True)
    for name in sorted_names:
        if name in query:
            entity = _ENTITY_DICT[name]
            if entity["id"] not in seen_ids:
                found.append({"name": name, **entity})
                seen_ids.add(entity["id"])

    return found


def _deepseek_llm(stream: bool = False) -> ChatOpenAI:
    return ChatOpenAI(
        model="deepseek-chat",
        api_key=settings.DEEPSEEK_API_KEY,
        base_url=DEEPSEEK_BASE,
        temperature=0.4,
        max_tokens=1200,
        streaming=stream,
    )


async def query_rewrite(state: AnalysisState) -> dict:
    """Rewrite user query: extract entities, map Chinese names, normalize for retrieval."""
    node = "query_rewrite"
    try:
        step_log = await push_step(state, node, "started", "Rewriting query...")

        original_query = state.get("query") or ""
        await _load_entity_dictionary()
        entities = _match_entities(original_query)

        # Build entity list string for LLM prompt
        entity_lines = ""
        if entities:
            entity_lines = "\n".join(
                f"- {e['type']}: {e['name']} (id={e['id']})" for e in entities
            )

        # If entities found or query is Chinese, use LLM to rewrite
        rewritten = original_query
        if entities or re.search(r"[\u4e00-\u9fff]", original_query):
            prompt = f"""You are a query normalization assistant for a football knowledge base.

Original user query: "{original_query}"

Known entities found in query:
{entity_lines or "(none)"}

Task:
1. Translate any Chinese football terms to English equivalents.
2. Replace player/team nicknames with standard names from the entity list.
3. Output a concise, standardized search query (1 short sentence).

Output ONLY the rewritten query text, nothing else."""

            llm = ChatOpenAI(
                model="deepseek-chat",
                api_key=settings.DEEPSEEK_API_KEY,
                base_url=DEEPSEEK_BASE,
                temperature=0.1,
                max_tokens=100,
            )
            resp = await llm.ainvoke([HumanMessage(content=prompt)])
            if resp.content:
                rewritten = resp.content.strip().strip('"').strip("'")

        step_log = await push_step(
            state, node, "completed",
            f"Rewritten: {rewritten[:80]}..." if len(rewritten) > 80 else f"Rewritten: {rewritten}"
        )
        existing = dict(state.get("analysis_result") or {})
        existing["rewritten_query"] = rewritten
        existing["extracted_entities"] = entities

        return {"step_log": step_log, "analysis_result": existing}

    except Exception as e:
        logger.warning("query_rewrite failed: %s, falling back to original", e)
        existing = dict(state.get("analysis_result") or {})
        existing["rewritten_query"] = state.get("query", "")
        existing["extracted_entities"] = []
        return {"step_log": await push_step(state, node, "completed", "Using original query"),
                "analysis_result": existing}


async def query_classify(state: AnalysisState) -> dict:
    node = "query_classify"
    try:
        step_log = await push_step(state, node, "started", "Classifying query intent...")
        ar = state.get("analysis_result") or {}
        # Use rewritten query if available, otherwise original
        query = ar.get("rewritten_query") or state.get("query") or ""
        levels = classify_query(query)
        step_log = await push_step(
            state, node, "completed",
            f"Query classified as: {', '.join(levels)}"
        )
        existing = dict(ar)
        existing["query_levels"] = levels
        return {"step_log": step_log, "analysis_result": existing}

    except Exception as e:
        step_log = await push_step(state, node, "failed", str(e))
        return {"step_log": step_log, "error": str(e)}


async def relevance_gate(state: AnalysisState) -> dict:
    """Route query based on football relevance and conversation turn count."""
    node = "relevance_gate"
    try:
        step_log = await push_step(state, node, "started", "Checking query relevance...")

        ar = state.get("analysis_result") or {}
        entities = ar.get("extracted_entities", [])
        qa_meta = ar.get("qa_meta", {})
        generic_turn_count = qa_meta.get("generic_turn_count", 0)
        football_intent_count = qa_meta.get("football_intent_count", 0)

        # Also check classify_query for football keywords not in entity dict
        query = state.get("query") or ""
        levels = classify_query(query)
        has_football_keywords = bool(levels and levels != ["tactical_level"])

        if entities or has_football_keywords:
            football_intent_count += 1
            generic_turn_count = 0
            route = "classify"
        else:
            generic_turn_count += 1
            if generic_turn_count > 3:
                route = "boundary_answer"
            else:
                route = "direct_answer"

        qa_meta["football_intent_count"] = football_intent_count
        qa_meta["generic_turn_count"] = generic_turn_count

        existing = dict(ar)
        existing["qa_meta"] = qa_meta
        existing["_route"] = route

        step_log = await push_step(
            state, node, "completed",
            f"Route: {route} (football={football_intent_count}, generic={generic_turn_count})"
        )
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
        # Use rewritten query if available
        query = ar.get("rewritten_query") or state.get("query") or ""

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


async def boundary_answer(state: AnalysisState) -> dict:
    """Generate boundary hint when user chats beyond 3 generic turns."""
    node = "boundary_answer"
    try:
        step_log = await push_step(state, node, "started", "Generating boundary hint...")

        lang = state.get("language", "en")
        query = state.get("query") or ""
        history = state.get("conversation_history") or []

        # Extract user name from history if available
        user_name = ""
        for turn in reversed(history):
            content = turn.get("content", "")
            if "我叫" in content or "我的名字是" in content:
                # Simple extraction: find text after "我叫"
                idx = content.find("我叫")
                if idx >= 0:
                    remainder = content[idx + 2:].strip()
                    # Take first word/name
                    user_name = remainder.split(",")[0].split("。")[0].split("，")[0].strip()
                    if user_name:
                        break

        name_prefix = f"{user_name}，" if user_name and lang == "zh" else ""

        if lang == "zh":
            system_prompt = f"""你是 AloFootMind，一位足球数据分析专家。
{name_prefix}你目前连续多轮没有提出足球相关的问题。
请礼貌地告知用户你的专长范围，并给出示例问题引导用户回到足球主题。

数据边界说明：
- 你目前仅有 2023/2024 赛季男子德甲联赛的数据
- 可以回答战术分析、球员数据、比赛情报等问题

回复要求：
1. 称呼用户名字（如果已知）
2. 说明数据边界
3. 给出 2-3 个示例问题
4. 语气友好专业
5. 如果用户用中文提问，用中文回复"""
        else:
            system_prompt = """You are AloFootMind, a football data analysis expert.
The user has been chatting without football-related questions for several turns.
Politely inform them of your scope and give example questions to guide them back.

Data scope: You only have 2023/2024 Bundesliga data.
You can answer tactical analysis, player stats, and match intelligence questions."""

        messages = [SystemMessage(content=system_prompt)]
        for turn in history[-3:]:
            if turn.get("role") == "user":
                messages.append(HumanMessage(content=turn["content"]))
            elif turn.get("role") == "assistant":
                messages.append(AIMessage(content=turn["content"]))
        messages.append(HumanMessage(content=query))

        llm = _deepseek_llm(stream=False)
        response = await llm.ainvoke(messages)

        step_log = await push_step(state, node, "completed", "Boundary hint generated.")
        return {"step_log": step_log, "report_markdown": response.content}

    except Exception as e:
        step_log = await push_step(state, node, "failed", str(e))
        return {"step_log": step_log, "error": str(e)}


async def direct_answer(state: AnalysisState) -> dict:
    """Direct LLM answer for generic conversation (within soft limit)."""
    node = "direct_answer"
    try:
        step_log = await push_step(state, node, "started", "Generating direct answer...")

        query = state.get("query") or ""
        history = state.get("conversation_history") or []
        lang = state.get("language", "en")

        system_prompt = (
            "You are AloFootMind, a friendly football expert assistant.\n"
            "You can engage in general conversation, remember user preferences, "
            "and answer casual questions.\n"
            "When the conversation turns to football, switch to data-driven analysis mode.\n"
            f"Current language: {'Chinese' if lang == 'zh' else 'English'}."
        )

        messages: list = [SystemMessage(content=system_prompt)]
        for turn in history[-5:]:
            if turn.get("role") == "user":
                messages.append(HumanMessage(content=turn["content"]))
            elif turn.get("role") == "assistant":
                messages.append(AIMessage(content=turn["content"]))
        messages.append(HumanMessage(content=query))

        llm = _deepseek_llm(stream=False)
        response = await llm.ainvoke(messages)

        step_log = await push_step(state, node, "completed", "Direct answer generated.")
        return {"step_log": step_log, "report_markdown": response.content}

    except Exception as e:
        step_log = await push_step(state, node, "failed", str(e))
        return {"step_log": step_log, "error": str(e)}


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

        lang = state.get("language", "en")
        if lang == "zh":
            system_prompt = """你是 AloFootMind，一位专业的足球数据分析 AI 助手。

你有两个信息来源：
1. RAG 上下文：从知识库检索到的足球数据（可能为空）。
   - 有 RAG 上下文时：基于它回答，并标注 [来源 N]。
   - 无 RAG 上下文时：直接说明"暂无相关数据"，不要编造。

2. 对话历史：本轮对话中用户告诉你的信息。
   - 你应该记住用户提到的个人信息（姓名、身份、偏好）。
   - 回答用户关于自己的问题时，从对话历史中提取。

数据边界：你目前仅有 2023/2024 赛季男子德甲联赛的数据。
请用 Markdown 格式回复。"""
        else:
            system_prompt = """You are AloFootMind, an expert AI football analyst.

You have access to two sources of information:
1. RAG CONTEXT: Football knowledge retrieved from the database (may be empty).
   - When RAG context is provided: base your answer on it and cite [Source N].
   - When RAG context is empty: simply say you don't have data for that query.

2. CONVERSATION HISTORY: Previous messages in this conversation.
   - Remember personal facts the user told you (name, role, preferences).
   - When answering questions about the user, extract from conversation history.

Data boundary: You only have data for the 2023/2024 Bundesliga season.
Format your answers in clear Markdown."""

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
            user_content = f"Question: {query}\n\n(No football data retrieved. Answer based on conversation history or general knowledge.)"

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
    language: str = "en",
) -> AsyncGenerator[str, None]:
    """Stream answer tokens for SSE — used directly by the /api/chat endpoint."""
    if rag_context:
        context_text = "\n\n".join(
            f"[Source {i+1}] {r['text']}" for i, r in enumerate(rag_context[:5])
        )
        user_content = f"Context from knowledge base:\n{context_text}\n\nQuestion: {query}"
        has_rag = True
    else:
        user_content = f"Question: {query}"
        has_rag = False

    if language == "zh":
        system_prompt = """你是 AloFootMind，一位专业的足球数据分析 AI 助手。

你有两个信息来源：
1. RAG 上下文：从知识库检索到的足球数据（可能为空）。
   - 有 RAG 上下文时：基于它回答，并标注 [来源 N]。
   - 无 RAG 上下文时：直接说明"暂无相关数据"，不要编造。

2. 对话历史：本轮对话中用户告诉你的信息。
   - 你应该记住用户提到的个人信息（姓名、身份、偏好）。
   - 回答用户关于自己的问题时，从对话历史中提取，不要用"根据提供的上下文"。

数据边界：你目前仅有 2023/2024 赛季男子德甲联赛的数据。
如果被问到其他联赛或赛季，请礼貌说明数据范围。

请用 Markdown 格式回复。"""
    else:
        system_prompt = """You are AloFootMind, an expert AI football analyst.

You have access to two sources of information:
1. RAG CONTEXT: Football knowledge retrieved from the database (may be empty).
   - When RAG context is provided: base your answer on it and cite [Source N].
   - When RAG context is empty: simply say you don't have data for that query. Do NOT fabricate.

2. CONVERSATION HISTORY: Previous messages in this conversation.
   - Remember personal facts the user told you (name, role, preferences).
   - When answering questions about the user, extract from conversation history.
     Do NOT say "based on the provided context" when referring to conversation history.

Data boundary: You only have data for the 2023/2024 Bundesliga season.
If asked about other leagues or seasons, politely state this limitation.

Format your answers in clear Markdown."""

    messages: list = [SystemMessage(content=system_prompt)]
    for turn in (conversation_history or [])[-5:]:
        if turn.get("role") == "user":
            messages.append(HumanMessage(content=turn["content"]))
        elif turn.get("role") == "assistant":
            messages.append(AIMessage(content=turn["content"]))

    if not has_rag:
        user_content += "\n\n(Note: No football data was retrieved for this query. Answer based on conversation history or general knowledge.)"

    messages.append(HumanMessage(content=user_content))

    llm = _deepseek_llm(stream=True)
    async for chunk in llm.astream(messages):
        if chunk.content:
            yield chunk.content


def _route(state: AnalysisState) -> str:
    """Conditional edge router from relevance_gate."""
    ar = state.get("analysis_result") or {}
    return ar.get("_route", "classify")


def build_qa_graph() -> StateGraph:
    graph = StateGraph(AnalysisState)
    graph.add_node("query_rewrite", query_rewrite)
    graph.add_node("relevance_gate", relevance_gate)
    graph.add_node("query_classify", query_classify)
    graph.add_node("rag_retrieval", rag_retrieval)
    graph.add_node("boundary_answer", boundary_answer)
    graph.add_node("direct_answer", direct_answer)
    graph.add_node("answer_generation", answer_generation)

    graph.set_entry_point("query_rewrite")
    graph.add_edge("query_rewrite", "relevance_gate")
    graph.add_conditional_edges(
        "relevance_gate",
        _route,
        {
            "classify": "query_classify",
            "boundary_answer": "boundary_answer",
            "direct_answer": "direct_answer",
        },
    )
    graph.add_edge("query_classify", "rag_retrieval")
    graph.add_edge("rag_retrieval", "answer_generation")
    graph.add_edge("answer_generation", END)
    graph.add_edge("boundary_answer", END)
    graph.add_edge("direct_answer", END)

    return graph.compile()
