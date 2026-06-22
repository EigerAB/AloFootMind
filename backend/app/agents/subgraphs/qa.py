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


async def _load_entity_dictionary() -> dict[str, dict]:
    """Load team & player names from PostgreSQL into memory cache (no aliases)."""
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

        # Detect data-scope queries: user asking what data/corpus the AI has
        _DATA_SCOPE_PATTERNS = [
            "掌握了哪些", "掌握哪些", "有哪些数据", "有什么数据", "有哪些语料", "有什么语料",
            "有哪些资料", "什么资料", "数据范围", "数据边界", "数据覆盖", "覆盖哪些",
            "知道哪些", "了解哪些赛事", "了解哪些联赛", "支持哪些", "支持什么联赛",
            "你的数据", "你有什么", "你有哪些", "你能分析哪", "你能查哪",
            "what data", "what leagues", "what competitions", "data coverage",
            "data range", "data scope", "which leagues", "which seasons",
        ]
        is_data_scope_query = any(p in query.lower() for p in _DATA_SCOPE_PATTERNS)

        if is_data_scope_query:
            route = "boundary_answer"
            # Don't increment generic counter for data-scope queries
        elif entities or has_football_keywords:
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


async def _fetch_player_candidates(query: str) -> list[dict]:
    """Fuzzy-search players in DB whose name appears relevant to the query keywords.
    Returns at most 8 candidates as {player_id, player_name} dicts.
    """
    _STOPWORDS = {"the", "and", "for", "are", "was", "were", "has", "have", "with", "that",
                  "this", "from", "their", "about", "between", "compare", "playing", "styles",
                  "differences", "characteristics", "features"}
    # Extract meaningful English words (≥4 chars, not stopwords)
    english_words = [w for w in re.findall(r'[A-Za-z]{4,}', query) if w.lower() not in _STOPWORDS]
    # Extract Chinese 3-char n-grams to match partial player names like "亚马尔", "姆巴佩"
    chinese_text = "".join(re.findall(r'[\u4e00-\u9fff]+', query))
    chinese_ngrams: list[str] = list(dict.fromkeys(
        chinese_text[i:i + 3] for i in range(len(chinese_text) - 2)
    ))
    # Prioritise Chinese ngrams first so they are not cut off by the limit
    words = list(dict.fromkeys(chinese_ngrams + english_words))[:20]
    if not words:
        return []
    async with AsyncSessionLocal() as session:
        conditions = " OR ".join([f"player_name ILIKE :w{i}" for i, _ in enumerate(words)])
        params = {f"w{i}": f"%{w}%" for i, w in enumerate(words)}
        result = await session.execute(
            text(f"SELECT player_id, player_name FROM players WHERE {conditions} LIMIT 8"),
            params,
        )
        return [{"player_id": row["player_id"], "player_name": row["player_name"]}
                for row in result.mappings()]


async def rag_plan(state: AnalysisState) -> dict:
    """LLM agent node: decide which collections to query, with which ID filters and top_k.
    Outputs a structured JSON plan stored in analysis_result['rag_plan'].
    Falls back to empty plan (rag_retrieval will use rule-based logic) on any error.
    """
    node = "rag_plan"
    try:
        step_log = await push_step(state, node, "started", "Planning retrieval strategy...")

        ar = state.get("analysis_result") or {}
        original_query = state.get("query") or ""
        rewritten_query = ar.get("rewritten_query") or original_query
        levels = ar.get("query_levels", [])

        # Build team candidates list from cached entity dict (deduplicated by id)
        await _load_entity_dictionary()
        seen_team_ids: set = set()
        unique_teams: list[str] = []
        for k, v in _ENTITY_DICT.items():
            if v["type"] == "team" and v["id"] not in seen_team_ids:
                seen_team_ids.add(v["id"])
                unique_teams.append(f"  - id={v['id']}, name={k}")
        team_list_str = "\n".join(unique_teams[:60])

        # Fetch player candidates via DB fuzzy search
        player_candidates = await _fetch_player_candidates(original_query + " " + rewritten_query)
        player_list_str = "\n".join(
            f"  - id={p['player_id']}, name={p['player_name']}" for p in player_candidates
        ) or "  (none found)"

        prompt = f"""You are a football knowledge base retrieval planner.

User query: "{original_query}"
Normalized query: "{rewritten_query}"
Pre-classified levels: {levels}

Available collections:
- team_tactical_profiles: aggregated tactical style per team (use when asking about a team's tactics, style, strengths)
- tactical_segments: match-level tactical clips (use when asking about specific match tactics or events)
- player_profiles: per-player stats and characteristics (use when asking about specific players)
- match_summaries: full match summary (use when asking about match results, scores, overview)

Available teams in database:
{team_list_str}

Available players matching this query:
{player_list_str}

Task: Output a JSON retrieval plan. For each collection to query, specify:
- "collection": one of the 4 collection names above
- "team_ids": list of team IDs to filter by, or null for no filter
- "player_ids": list of player IDs to filter by, or null
- "top_k": number of results to fetch (3-20)

Rules:
1. If the query mentions specific teams by name, use their IDs to filter team_tactical_profiles — one entry per team, top_k=3
2. If the query mentions specific players by name AND they appear in the "Available players" list, create ONE player_profiles entry PER player with only that player's ID and top_k=3 — do NOT combine multiple players into one entry
3. Only use player IDs from the "Available players" list above — never invent IDs
4. If the query asks about players in general (e.g. "outstanding forwards", "top scorers") but no specific player is matched, add ONE player_profiles entry with player_ids=null and top_k=10; if the query also mentions a specific team, combine with that team's team_ids filter
5. Add tactical_segments or match_summaries only if the query is about specific matches or tactical clips
6. Do NOT add a collection if it is irrelevant to the query

Output ONLY valid JSON, no explanation:
{{"retrievals": [...]}}"""

        llm = get_deepseek_llm(temperature=0, max_tokens=400, request_timeout=20)
        resp = await asyncio.wait_for(llm.ainvoke([HumanMessage(content=prompt)]), timeout=20.0)
        raw = resp.content.strip()

        # Extract JSON from response (handle possible markdown code fences)
        json_match = re.search(r'\{.*\}', raw, re.DOTALL)
        plan: list[dict] = []
        if json_match:
            import json as _json
            try:
                parsed = _json.loads(json_match.group())
                plan = parsed.get("retrievals", [])
            except Exception:
                pass

        summary_parts = []
        for r in plan:
            col = r.get("collection", "?")
            tids = r.get("team_ids")
            pids = r.get("player_ids")
            k = r.get("top_k", "?")
            if tids:
                summary_parts.append(f"{col}(teams={tids},k={k})")
            elif pids:
                summary_parts.append(f"{col}(players={pids},k={k})")
            else:
                summary_parts.append(f"{col}(k={k})")

        summary = "Plan: " + ", ".join(summary_parts) if summary_parts else "No plan generated, using fallback"
        step_log = await push_step(state, node, "completed", summary, data={"plan": plan})

        existing = dict(ar)
        existing["rag_plan"] = plan
        return {"step_log": step_log, "analysis_result": existing}

    except Exception as e:
        logger.warning("rag_plan failed: %s, falling back to rule-based retrieval", e)
        step_log = await push_step(state, node, "completed", f"Fallback: {str(e)[:60]}")
        existing = dict(state.get("analysis_result") or {})
        existing["rag_plan"] = []
        return {"step_log": step_log, "analysis_result": existing}


COLLECTION_LEVEL_MAP = {
    "team_tactical_profiles": "team_tactical_level",
    "tactical_segments": "tactical_level",
    "player_profiles": "player_level",
    "match_summaries": "match_level",
}


async def rag_retrieval(state: AnalysisState) -> dict:
    node = "rag_retrieval"
    try:
        step_log = await push_step(state, node, "started", "Searching knowledge base...")

        ar = state.get("analysis_result") or {}
        query = ar.get("rewritten_query") or state.get("query") or ""
        plan: list[dict] = ar.get("rag_plan", [])

        # ── Path A: execute rag_plan if provided and non-empty ──────────────────
        if plan:
            all_results: list[dict] = []
            seen_texts: set[str] = set()
            for item in plan:
                col = item.get("collection", "")
                level = COLLECTION_LEVEL_MAP.get(col)
                if not level:
                    continue
                team_ids = item.get("team_ids") or []
                player_ids = item.get("player_ids") or []
                top_k = int(item.get("top_k", 3))

                if team_ids:
                    for tid in team_ids:
                        hits = await retrieve(
                            query=query,
                            top_k=top_k,
                            team_id=tid,
                            force_levels=[level],
                            score_threshold=None,
                        )
                        for h in hits:
                            if h["text"] not in seen_texts:
                                seen_texts.add(h["text"])
                                all_results.append(h)
                elif player_ids:
                    for pid in player_ids:
                        hits = await retrieve(
                            query=query,
                            top_k=top_k,
                            player_ids=[pid],
                            force_levels=[level],
                            score_threshold=None,
                        )
                        for h in hits:
                            if h["text"] not in seen_texts:
                                seen_texts.add(h["text"])
                                all_results.append(h)
                else:
                    hits = await retrieve(
                        query=query,
                        top_k=top_k,
                        force_levels=[level],
                        score_threshold=None,
                    )
                    for h in hits:
                        if h["text"] not in seen_texts:
                            seen_texts.add(h["text"])
                            all_results.append(h)
            results = all_results

        # ── Path B: rule-based fallback (no rag_plan) ───────────────────────────
        else:
            levels = ar.get("query_levels", ["tactical_level"])
            if "match_level" in levels:
                if "tactical_level" not in levels:
                    levels = levels + ["tactical_level"]
                if "team_tactical_level" not in levels:
                    levels = levels + ["team_tactical_level"]

            entities = ar.get("extracted_entities", [])
            team_ids_in_query = [e["id"] for e in entities if e["type"] == "team"]
            player_ids_in_query = [e["id"] for e in entities if e["type"] == "player"]
            team_id_filter = team_ids_in_query[0] if len(team_ids_in_query) == 1 else None

            if len(player_ids_in_query) > 1 and "player_level" in levels:
                other_levels = [l for l in levels if l != "player_level"]
                per_player: list[dict] = []
                for pid in player_ids_in_query:
                    per_player.extend(await retrieve(query=query, top_k=2, player_ids=[pid],
                                                     force_levels=["player_level"], score_threshold=None))
                other = await retrieve(query=query, top_k=10, team_id=team_id_filter,
                                       force_levels=other_levels or ["tactical_level"],
                                       score_threshold=None) if other_levels else []
                seen = {r["text"] for r in per_player}
                results = per_player + [r for r in other if r["text"] not in seen]

            elif len(team_ids_in_query) > 1 and "team_tactical_level" in levels:
                other_levels = [l for l in levels if l != "team_tactical_level"]
                per_team: list[dict] = []
                for tid in team_ids_in_query:
                    per_team.extend(await retrieve(query=query, top_k=3, team_id=tid,
                                                   force_levels=["team_tactical_level"], score_threshold=None))
                other = await retrieve(query=query, top_k=10, team_id=None,
                                       force_levels=other_levels or ["tactical_level"],
                                       score_threshold=None) if other_levels else []
                seen = {r["text"] for r in per_team}
                results = per_team + [r for r in other if r["text"] not in seen]

            else:
                results = await retrieve(
                    query=query, top_k=10, team_id=team_id_filter,
                    player_ids=player_ids_in_query if player_ids_in_query else None,
                    force_levels=levels, score_threshold=None,
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

    # Detect if this is an explicit data-scope query
    _DATA_SCOPE_PATTERNS = [
        "掌握了哪些", "掌握哪些", "有哪些数据", "有什么数据", "有哪些语料", "有什么语料",
        "有哪些资料", "什么资料", "数据范围", "数据边界", "数据覆盖", "覆盖哪些",
        "知道哪些", "了解哪些赛事", "了解哪些联赛", "支持哪些", "支持什么联赛",
        "你的数据", "你有什么", "你有哪些", "你能分析哪", "你能查哪",
        "what data", "what leagues", "what competitions", "data coverage",
        "data range", "data scope", "which leagues", "which seasons",
    ]
    is_data_scope_query = any(p in query.lower() for p in _DATA_SCOPE_PATTERNS)

    if lang == "zh":
        if is_data_scope_query:
            system_prompt = f"""你是 AloFootMind，一位足球数据分析专家。
用户想了解你掌握的数据范围，请准确、清晰地说明以下数据边界，不要编造或夸大。

## 你的数据边界（严格按此回答）

**赛事覆盖：**
- 2023/2024 赛季 男子德甲联赛（Bundesliga，第1轮至第34轮）
- 2024 年 欧洲杯（UEFA Euro 2024，小组赛至决赛）

**数据类型：**
- 比赛事件数据：进球、助攻、射门、传球、抢断、犯规、黄/红牌等逐场记录
- 阵容与出场：每场比赛的首发/替补、上下场时间
- 球员档案：基本信息、赛季累计数据（进球/助攻/出场次数/预期进球 xG 等）
- 球队风格标签：控球率、高位压迫、防守体系等战术特征

**不在数据范围内：**
- 其他联赛（英超、西甲、意甲、法甲、冠军联赛等）
- 2023/2024 赛季以外的历史数据
- 实时/最新赛事数据（数据截至 2024 年欧洲杯决赛）
- 转会市场、合同、薪资等商业数据

回复要求：
1. 先清晰列出数据边界
2. 再给出 2-3 个可以回答的示例问题
3. 语气简洁专业
4. 用中文回复"""
        else:
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
        if is_data_scope_query:
            system_prompt = """You are AloFootMind, a football data analysis expert.
The user wants to know exactly what data you have. Answer precisely based on the following scope only — do not fabricate or exaggerate.

## Your Data Scope

**Competitions covered:**
- 2023/2024 Bundesliga (all 34 matchdays)
- UEFA Euro 2024 (group stage through final)

**Data types available:**
- Match events: goals, assists, shots, passes, tackles, fouls, cards — per match
- Lineups: starters, substitutes, and timing
- Player profiles: career stats, season totals (goals/assists/xG/appearances)
- Team style tags: possession, high press, defensive shape, etc.

**NOT in scope:**
- Other leagues (Premier League, La Liga, Serie A, Champions League, etc.)
- Seasons other than 2023/2024 / Euro 2024
- Real-time or post-Euro 2024 data
- Transfer market, contracts, or salary data

Give 2-3 example questions you can answer at the end."""
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
    graph.add_node("rag_plan", rag_plan)
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
    graph.add_edge("query_classify", "rag_plan")
    graph.add_edge("rag_plan", "rag_retrieval")
    graph.add_edge("rag_retrieval", END)

    return graph.compile()
