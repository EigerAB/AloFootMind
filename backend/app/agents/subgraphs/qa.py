"""QA Sub-graph: query_rewrite → relevance_gate → query_classify → rag_retrieval.

The graph is a pure router + retriever. Answer generation (streaming) is handled
by the endpoint layer via stream_answer / stream_direct_answer / stream_boundary_answer.
"""
from __future__ import annotations

import asyncio
import logging
import re
from typing import AsyncGenerator

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.graph import END, StateGraph
from sqlalchemy import text

from app.agents.state import AnalysisState
from app.agents.utils import push_step
from app.db.postgres import AsyncSessionLocal
from app.services.llm_client import get_deepseek_llm
from app.services.rag_service import classify_query, retrieve

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
#  Entity Dictionary (teams + players from DB)
# ─────────────────────────────────────────────
_ENTITY_DICT: dict[str, dict] = {}
# e.g. {"勒沃库森": {"id": 904, "type": "team"}, ...}


# Common Chinese player name → English name as stored in DB
_PLAYER_ALIASES: dict[str, str] = {
    "凯恩": "Harry Kane",
    "穆勒": "Thomas Müller",
    "穆西亚拉": "Jamal Musiala",
    "格雷茨卡": "Leon Goretzka",
    "基米希": "Joshua Kimmich",
    "诺伊尔": "Manuel Neuer",
    "萨内": "Leroy Sané",
    "科曼": "Kingsley Coman",
    "格纳布里": "Serge Gnabry",
    "帕利尼亚": "João Palhinha",
    "格拉内罗": "Granit Xhaka",
    "赫拉特": "Granit Xhaka",
    "沙卡": "Bukayo Saka",
    "特尔": "Florian Wirtz",
    "维尔茨": "Florian Wirtz",
    "格里马尔多": "Alejandro Grimaldo",
    "齐默尔曼": "Lukas Hradecky",
    "本塞拜尼": "Granit Xhaka",
    "多亚克": "Patrik Schick",
    "霍夫曼": "Jonas Hofmann",
    "安德里奇": "Robert Andrich",
    "塔": "Edmond Tapsoba",
    "克拉默": "Florian Kramer",
    "哈弗茨": "Kai Havertz",
    "克罗斯": "Toni Kroos",
    "京多安": "İlkay Gündoğan",
    "胡梅尔斯": "Mats Hummels",
    "布兰特": "Julian Brandt",
    "罗伊斯": "Marco Reus",
    "萨拉比亚": "Pablo Sarabia",
    "亚马尔": "Lamine Yamal",
    "佩德里": "Pedri",
    "科利亚西亚斯": "Alejandro Balde",
    "费兰托雷斯": "Ferran Torres",
    "莫拉塔": "Álvaro Morata",
    "罗德里": "Rodri",
    "法比安": "Fabián Ruiz",
    "卡瓦哈尔": "Dani Carvajal",
    "纳乔": "Nacho",
    "勒诺曼": "William Saliba",
    "姆巴佩": "Kylian Mbappé",
    "格列兹曼": "Antoine Griezmann",
    "坎特": "N'Golo Kanté",
    "图拉姆": "Marcus Thuram",
    "吉鲁": "Olivier Giroud",
    "帕瓦尔": "Benjamin Pavard",
    "科纳特": "Ibrahima Konaté",
    "索勒": "Carlos Soler",
    "奥利莫": "Nico Williams",
}

# Common Chinese team name abbreviations → canonical name suffix to match DB
_TEAM_ALIASES: dict[str, str] = {
    "拜仁": "拜仁慕尼黑",
    "多特": "多特蒙德",
    "门兴": "门兴格拉德巴赫",
    "莱比锡": "莱比锡红牛",
    "不莱梅": "云达不莱梅",
    "沙尔克": "沙尔克04",
    "柏林联": "柏林联合",
    "海登海": "海登海姆",
    "达姆": "达姆施塔特",
    "霍芬": "霍芬海姆",
}


async def _load_entity_dictionary() -> dict[str, dict]:
    """Load team & player names from PostgreSQL into memory cache."""
    global _ENTITY_DICT
    if _ENTITY_DICT:
        return _ENTITY_DICT

    async with AsyncSessionLocal() as session:
        # Teams (Chinese names)
        team_result = await session.execute(text("SELECT team_id, team_name FROM teams"))
        team_rows = list(team_result.mappings())
        canonical: dict[str, dict] = {}
        for row in team_rows:
            name = row["team_name"]
            if name:
                entry = {"id": row["team_id"], "type": "team"}
                _ENTITY_DICT[name] = entry
                canonical[name] = entry

        # Register team aliases: "拜仁" → same entry as "拜仁慕尼黑"
        for alias, full_name in _TEAM_ALIASES.items():
            if full_name in canonical and alias not in _ENTITY_DICT:
                _ENTITY_DICT[alias] = canonical[full_name]

        # Players (English names from DB)
        player_result = await session.execute(text("SELECT player_id, player_name FROM players"))
        player_canonical: dict[str, dict] = {}
        for row in player_result.mappings():
            name = row["player_name"]
            if name:
                entry = {"id": row["player_id"], "type": "player"}
                _ENTITY_DICT[name] = entry
                player_canonical[name] = entry

        # Register player aliases: "凯恩" → same entry as "Harry Kane"
        for alias, full_name in _PLAYER_ALIASES.items():
            if full_name in player_canonical and alias not in _ENTITY_DICT:
                _ENTITY_DICT[alias] = player_canonical[full_name]

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
3. Output a concise, standardized search query (1 short sentence) in English.

Output ONLY the rewritten English query text, nothing else."""

            llm = get_deepseek_llm(
                temperature=0.1,
                max_tokens=100,
                request_timeout=15,
            )
            resp = await asyncio.wait_for(llm.ainvoke([HumanMessage(content=prompt)]), timeout=15.0)
            if resp.content:
                rewritten = resp.content.strip().strip('"').strip("'")

        # Build a bilingual search query: combine original Chinese + English rewrite
        # so that Milvus sparse (BM25) can match Chinese tokens while dense covers English semantics
        if rewritten != original_query and re.search(r"[\u4e00-\u9fff]", original_query):
            bilingual_query = f"{original_query} {rewritten}"
        else:
            bilingual_query = rewritten

        step_log = await push_step(
            state, node, "completed",
            f"Rewritten: {rewritten[:80]}..." if len(rewritten) > 80 else f"Rewritten: {rewritten}"
        )
        existing = dict(state.get("analysis_result") or {})
        existing["rewritten_query"] = bilingual_query
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
        # If player entities were extracted in query_rewrite, force player_level
        # (regex-based classify only matches generic keywords like "player", not proper names)
        entities = ar.get("extracted_entities", [])
        if any(e["type"] == "player" for e in entities) and "player_level" not in levels:
            levels = ["player_level"] + levels
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
        # Expand match-level queries to also retrieve tactical data
        if "match_level" in levels:
            if "tactical_level" not in levels:
                levels = levels + ["tactical_level"]
            if "team_tactical_level" not in levels:
                levels = levels + ["team_tactical_level"]
        # Use rewritten (bilingual) query if available
        query = ar.get("rewritten_query") or state.get("query") or ""

        # Extract entity filters from matched entities
        entities = ar.get("extracted_entities", [])
        team_ids_in_query = [e["id"] for e in entities if e["type"] == "team"]
        player_ids_in_query = [e["id"] for e in entities if e["type"] == "player"]
        team_id_filter = team_ids_in_query[0] if len(team_ids_in_query) == 1 else None

        # For multi-player queries: retrieve player_profiles separately per player
        # so each player gets equal representation
        if len(player_ids_in_query) > 1 and "player_level" in levels:
            other_levels = [l for l in levels if l != "player_level"]
            per_player_results: list[dict] = []
            for pid in player_ids_in_query:
                player_hits = await retrieve(
                    query=query,
                    top_k=2,
                    player_ids=[pid],
                    force_levels=["player_level"],
                    score_threshold=None,
                )
                per_player_results.extend(player_hits)
            other_results = await retrieve(
                query=query,
                top_k=10,
                team_id=team_id_filter,
                force_levels=other_levels if other_levels else ["tactical_level"],
                score_threshold=None,
            ) if other_levels else []
            seen_texts: set[str] = {r["text"] for r in per_player_results}
            deduped_other = [r for r in other_results if r["text"] not in seen_texts]
            results = per_player_results + deduped_other

        # For multi-team queries: retrieve team_tactical_profiles separately per team
        # so each team gets equal representation, then retrieve other levels normally
        elif len(team_ids_in_query) > 1 and "team_tactical_level" in levels:
            other_levels = [l for l in levels if l != "team_tactical_level"]
            per_team_results: list[dict] = []
            for tid in team_ids_in_query:
                team_hits = await retrieve(
                    query=query,
                    top_k=3,
                    team_id=tid,
                    force_levels=["team_tactical_level"],
                    score_threshold=None,
                )
                per_team_results.extend(team_hits)
            other_results = await retrieve(
                query=query,
                top_k=10,
                team_id=None,
                force_levels=other_levels if other_levels else ["tactical_level"],
                score_threshold=None,
            ) if other_levels else []
            seen_texts = {r["text"] for r in per_team_results}
            deduped_other = [r for r in other_results if r["text"] not in seen_texts]
            results = per_team_results + deduped_other

        else:
            results = await retrieve(
                query=query,
                top_k=10,
                team_id=team_id_filter,
                player_ids=player_ids_in_query if player_ids_in_query else None,
                force_levels=levels,
                score_threshold=None,
            )

        if not results:
            step_log = await push_step(state, node, "completed", "No matching documents found.")
        else:
            step_log = await push_step(
                state, node, "completed",
                f"Retrieved {len(results)} relevant documents (team_id_filter={team_id_filter})."
            )
        return {"step_log": step_log, "rag_context": results}

    except Exception as e:
        step_log = await push_step(state, node, "failed", str(e))
        return {"step_log": step_log, "rag_context": [], "error": str(e)}


async def stream_boundary_answer(
    query: str,
    conversation_history: list[dict],
    language: str = "zh",
) -> AsyncGenerator[str, None]:
    """Stream a boundary hint when the user has exceeded 3 generic turns."""
    lang = language
    history = conversation_history or []

    user_name = ""
    for turn in reversed(history):
        content = turn.get("content", "")
        if "我叫" in content or "我的名字是" in content:
            idx = content.find("我叫")
            if idx >= 0:
                remainder = content[idx + 2:].strip()
                user_name = remainder.split(",")[0].split("。")[0].split("，")[0].strip()
                if user_name:
                    break

    name_prefix = f"{user_name}，" if user_name and lang == "zh" else ""

    if lang == "zh":
        system_prompt = f"""你是 AloFootMind，一位足球数据分析专家。
{name_prefix}你目前连续多轮没有提出足球相关的问题。
请礼貌地告知用户你的专长范围，并给出示例问题引导用户回到足球主题。

数据边界说明：
- 你目前拥有 2023/2024 赛季男子德甲联赛和 2024 年欧洲杯的数据
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

Data scope: You have 2023/2024 Bundesliga and UEFA Euro 2024 data.
You can answer tactical analysis, player stats, and match intelligence questions."""

    messages: list = [SystemMessage(content=system_prompt)]
    for turn in history[-3:]:
        if turn.get("role") == "user":
            messages.append(HumanMessage(content=turn["content"]))
        elif turn.get("role") == "assistant":
            messages.append(AIMessage(content=turn["content"]))
    messages.append(HumanMessage(content=query))

    llm = get_deepseek_llm(streaming=True, temperature=0.4, max_tokens=1200, request_timeout=25)
    async for chunk in llm.astream(messages):
        if chunk.content:
            yield chunk.content
        await asyncio.sleep(0)


async def stream_direct_answer(
    query: str,
    conversation_history: list[dict],
    language: str = "zh",
) -> AsyncGenerator[str, None]:
    """Stream a direct conversational reply (no RAG) for generic turns within the soft limit."""
    lang = language
    system_prompt = (
        "You are AloFootMind, a friendly football expert assistant.\n"
        "You can engage in general conversation, remember user preferences, "
        "and answer casual questions.\n"
        "When the conversation turns to football, switch to data-driven analysis mode.\n"
        f"Current language: {'Chinese' if lang == 'zh' else 'English'}."
    )

    messages: list = [SystemMessage(content=system_prompt)]
    for turn in (conversation_history or [])[-5:]:
        if turn.get("role") == "user":
            messages.append(HumanMessage(content=turn["content"]))
        elif turn.get("role") == "assistant":
            messages.append(AIMessage(content=turn["content"]))
    messages.append(HumanMessage(content=query))

    llm = get_deepseek_llm(streaming=True, temperature=0.4, max_tokens=1200, request_timeout=25)
    async for chunk in llm.astream(messages):
        if chunk.content:
            yield chunk.content
        await asyncio.sleep(0)




def _extract_user_profile(conversation_history: list[dict]) -> str:
    """Scan full history for user-stated personal facts (name, role, preferences)."""
    facts: list[str] = []
    name_patterns = [r"我叫(\S+)", r"我的名字(?:是|叫)(\S+)", r"my name is (\w+)", r"i['']m (\w+),?\s*(a|an)?"]
    role_patterns = [r"我是(?:一名|一个)?(.{2,20}?)[，,。\s]", r"i(?:'m| am) (?:a |an )?(.{2,30}?)(?:[,.]|$)"]
    for turn in conversation_history:
        if turn.get("role") != "user":
            continue
        content = turn.get("content", "")
        for pat in name_patterns:
            m = re.search(pat, content, re.IGNORECASE)
            if m:
                facts.append(f"用户姓名：{m.group(1).strip()}")
                break
        for pat in role_patterns:
            m = re.search(pat, content, re.IGNORECASE)
            if m:
                role = m.group(1).strip().rstrip("，。,.").strip()
                if role:
                    facts.append(f"用户身份：{role}")
                break
    # Deduplicate keeping last occurrence of each fact type
    seen: dict[str, str] = {}
    for f in facts:
        key = f.split("：")[0]
        seen[key] = f
    return "\n".join(seen.values())


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

    # Extract user profile from full history and pin it into system prompt
    user_profile = _extract_user_profile(conversation_history or [])
    profile_section = f"\n\n【用户信息（始终记住）】\n{user_profile}" if user_profile else ""

    if language == "zh":
        system_prompt = f"""你是 AloFootMind，一位专业的足球数据分析 AI 助手。{profile_section}

你有两个信息来源：
1. RAG 上下文：从知识库检索到的足球数据（可能为空）。
   - 有 RAG 上下文时：基于它回答，并标注 [来源 N]。
   - 无 RAG 上下文时：直接说明"暂无相关数据"，不要编造。

2. 对话历史：本轮对话中用户告诉你的信息。
   - 你应该记住用户提到的个人信息（姓名、身份、偏好）。
   - 回答用户关于自己的问题时，优先从【用户信息】区块提取，不要用"根据提供的上下文"。

数据边界：你目前拥有 2023/2024 赛季男子德甲联赛和 2024 年欧洲杯（UEFA Euro 2024）的数据。
当被问到其他联赛或赛季时，请礼貌说明数据范围。

请用 Markdown 格式回复。"""
    else:
        system_prompt = f"""You are AloFootMind, an expert AI football analyst.{profile_section}

You have access to two sources of information:
1. RAG CONTEXT: Football knowledge retrieved from the database (may be empty).
   - When RAG context is provided: base your answer on it and cite [Source N].
   - When RAG context is empty: simply say you don't have data for that query. Do NOT fabricate.

2. CONVERSATION HISTORY: Previous messages in this conversation.
   - Remember personal facts the user told you (name, role, preferences).
   - When answering questions about the user, extract from the user profile above.
     Do NOT say "based on the provided context" when referring to user facts.

Data boundary: You have data for the 2023/2024 Bundesliga season and UEFA Euro 2024.
If asked about other leagues or seasons, politely state this limitation.

Format your answers in clear Markdown."""

    messages: list = [SystemMessage(content=system_prompt)]
    for turn in (conversation_history or [])[-20:]:
        if turn.get("role") == "user":
            messages.append(HumanMessage(content=turn["content"]))
        elif turn.get("role") == "assistant":
            messages.append(AIMessage(content=turn["content"]))

    if not has_rag:
        user_content += "\n\n(Note: No football data was retrieved for this query. Answer based on conversation history or general knowledge.)"

    messages.append(HumanMessage(content=user_content))

    llm = get_deepseek_llm(streaming=True, temperature=0.4, max_tokens=1200, request_timeout=25)
    async for chunk in llm.astream(messages):
        if chunk.content:
            yield chunk.content
        await asyncio.sleep(0)  # yield control to event loop


def _route(state: AnalysisState) -> str:
    """Conditional edge router from relevance_gate."""
    ar = state.get("analysis_result") or {}
    return ar.get("_route", "classify")


def build_qa_graph() -> StateGraph:
    """Pure router + retriever graph.

    All three paths terminate at END after setting analysis_result._route.
    The endpoint layer reads _route and dispatches to the appropriate
    stream_answer / stream_direct_answer / stream_boundary_answer generator.
    """
    graph = StateGraph(AnalysisState)
    graph.add_node("query_rewrite", query_rewrite)
    graph.add_node("relevance_gate", relevance_gate)
    graph.add_node("query_classify", query_classify)
    graph.add_node("rag_retrieval", rag_retrieval)

    graph.set_entry_point("query_rewrite")
    graph.add_edge("query_rewrite", "relevance_gate")
    graph.add_conditional_edges(
        "relevance_gate",
        _route,
        {
            "classify": "query_classify",
            "boundary_answer": END,
            "direct_answer": END,
        },
    )
    graph.add_edge("query_classify", "rag_retrieval")
    graph.add_edge("rag_retrieval", END)

    return graph.compile()
