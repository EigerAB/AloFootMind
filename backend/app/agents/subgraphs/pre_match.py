"""PreMatch Sub-graph: fetch_team_history → rag_retrieval → matchup_analysis → intelligence_report."""
from __future__ import annotations

import json
import logging

from langchain_core.messages import HumanMessage
from langgraph.graph import END, StateGraph

from app.agents.state import AnalysisState
from app.agents.utils import extract_key_players, llm_retry, push_step, set_task_result, set_task_status
from app.services.llm_client import get_deepseek_llm
from app.services.rag_service import retrieve

logger = logging.getLogger(__name__)

_STEP_MSGS: dict[str, dict[str, dict[str, str]]] = {
    "fetch_team_history": {
        "en": {
            "started": "Loading team historical data...",
            "completed": "Found {n} head-to-head matches for {home} vs {away}.",
            "failed": "Need 2 team IDs.",
        },
        "zh": {
            "started": "正在加载球队历史数据...",
            "completed": "找到 {n} 场 {home} vs {away} 的两队相遇记录。",
            "failed": "需要 2 个球队 ID。",
        },
    },
    "rag_retrieval": {
        "en": {
            "started": "Searching match summaries, tactical segments and player profiles...",
            "completed": "Retrieved {n} relevant documents.",
        },
        "zh": {
            "started": "正在检索比赛摘要、战术片段和球员画像...",
            "completed": "已检索到 {n} 条相关语料。",
        },
    },
    "matchup_analysis": {
        "en": {
            "started": "Running LLM matchup analysis...",
            "completed": "Matchup analysis complete.",
        },
        "zh": {
            "started": "正在运行 GPT-4o 对阵分析...",
            "completed": "对阵分析完成。",
        },
    },
    "intelligence_report": {
        "en": {
            "started": "Generating intelligence report...",
            "completed": "Intelligence report saved.",
        },
        "zh": {
            "started": "正在生成情报报告...",
            "completed": "情报报告已保存。",
        },
    },
}


def _msg(node: str, key: str, lang: str, **kwargs: object) -> str:
    tmpl = _STEP_MSGS.get(node, {}).get(lang, _STEP_MSGS.get(node, {}).get("en", {})).get(key, key)
    return tmpl.format(**kwargs) if kwargs else tmpl




async def fetch_team_history(state: AnalysisState) -> dict:
    node = "fetch_team_history"
    lang = state.get("language", "en")
    try:
        step_log = await push_step(state, node, "started", _msg(node, "started", lang))

        from sqlalchemy import text
        from app.db.postgres import AsyncSessionLocal

        team_ids = state.get("team_ids") or []
        if len(team_ids) < 2:
            return {"step_log": await push_step(state, node, "failed", _msg(node, "failed", lang)),
                    "error": "Insufficient team IDs"}

        home_id, away_id = team_ids[0], team_ids[1]

        async with AsyncSessionLocal() as session:
            team_rows = await session.execute(
                text("SELECT team_id, team_name FROM teams WHERE team_id IN (:h, :a)"),
                {"h": home_id, "a": away_id},
            )
            teams = {r[0]: r[1] for r in team_rows}

            history = await session.execute(
                text("""
                    SELECT m.match_id, m.match_date, m.home_score, m.away_score,
                           ht.team_name AS home_name, at.team_name AS away_name,
                           m.home_formation, m.away_formation,
                           ea.home_shots, ea.away_shots
                    FROM matches m
                    JOIN teams ht ON m.home_team_id = ht.team_id
                    JOIN teams at ON m.away_team_id = at.team_id
                    LEFT JOIN events_aggregated ea ON m.match_id = ea.match_id
                    WHERE (m.home_team_id = :h AND m.away_team_id = :a)
                       OR (m.home_team_id = :a AND m.away_team_id = :h)
                    ORDER BY m.match_date DESC
                    LIMIT 10
                """),
                {"h": home_id, "a": away_id},
            )
            h2h_matches = [dict(r) for r in history.mappings()]

        h2h_data = [
            {
                "match_date": str(m["match_date"]),
                "home_name": m["home_name"],
                "away_name": m["away_name"],
                "home_score": m["home_score"],
                "away_score": m["away_score"],
                "home_formation": m["home_formation"],
                "away_formation": m["away_formation"],
            }
            for m in h2h_matches
        ]
        step_log = await push_step(
            state, node, "completed",
            _msg(node, "completed", lang, n=len(h2h_matches),
                 home=teams.get(home_id, home_id), away=teams.get(away_id, away_id)),
            data={"h2h_matches": h2h_data},
        )
        return {
            "step_log": step_log,
            "analysis_result": {
                "teams": teams,
                "home_id": home_id,
                "away_id": away_id,
                "h2h_matches": h2h_matches,
            },
        }

    except Exception as e:
        await set_task_status(state["task_id"], "failed")
        step_log = await push_step(state, node, "error", str(e))
        return {"step_log": step_log, "error": str(e)}


async def rag_retrieval(state: AnalysisState) -> dict:
    node = "rag_retrieval"
    lang = state.get("language", "en")
    try:
        step_log = await push_step(state, node, "started", _msg(node, "started", lang))

        from sqlalchemy import text
        from app.db.postgres import AsyncSessionLocal

        ar = state.get("analysis_result") or {}
        teams = ar.get("teams", {})
        home_id = ar.get("home_id")
        away_id = ar.get("away_id")
        home_name = teams.get(home_id, "Home team")
        away_name = teams.get(away_id, "Away team")

        h2h_matches = ar.get("h2h_matches", [])
        h2h_match_ids = {m["match_id"] for m in h2h_matches}
        h2h_latest_id = h2h_matches[0]["match_id"] if h2h_matches else None

        h2h_key_events: list[dict] = []
        home_last_id = None
        home_key_events: list[dict] = []
        away_last_id = None
        away_key_events: list[dict] = []

        async with AsyncSessionLocal() as session:
            # 1) h2h 最近一场的 key_events
            if h2h_latest_id:
                result = await session.execute(
                    text("SELECT key_events_json FROM events_aggregated WHERE match_id = :mid"),
                    {"mid": h2h_latest_id},
                )
                row = result.mappings().first()
                if row:
                    h2h_key_events = json.loads(row["key_events_json"] or "[]")

            # 2) 主队最近一场（排除 h2h）
            home_result = await session.execute(
                text("""
                    SELECT m.match_id, ea.key_events_json
                    FROM matches m
                    LEFT JOIN events_aggregated ea ON m.match_id = ea.match_id
                    WHERE (m.home_team_id = :tid OR m.away_team_id = :tid)
                    ORDER BY m.match_date DESC
                    LIMIT 3
                """),
                {"tid": home_id},
            )
            for row in home_result.mappings():
                if row["match_id"] not in h2h_match_ids:
                    home_last_id = row["match_id"]
                    home_key_events = json.loads(row["key_events_json"] or "[]")
                    break

            # 3) 客队最近一场（排除 h2h）
            away_result = await session.execute(
                text("""
                    SELECT m.match_id, ea.key_events_json
                    FROM matches m
                    LEFT JOIN events_aggregated ea ON m.match_id = ea.match_id
                    WHERE (m.home_team_id = :tid OR m.away_team_id = :tid)
                    ORDER BY m.match_date DESC
                    LIMIT 3
                """),
                {"tid": away_id},
            )
            for row in away_result.mappings():
                if row["match_id"] not in h2h_match_ids:
                    away_last_id = row["match_id"]
                    away_key_events = json.loads(row["key_events_json"] or "[]")
                    break

        # 4) 三维度检索
        all_results: list[dict] = []

        # match_level: 仅 h2h 最近一场的 match summaries
        if h2h_latest_id:
            match_results = await retrieve(
                query=f"{home_name} vs {away_name} match summary",
                top_k=2,
                match_ids=[h2h_latest_id],
                force_levels=["match_level"],
            )
            all_results.extend(match_results)

        # tactical_level: h2h + 主队最近 + 客队最近
        tactical_match_ids = [mid for mid in [h2h_latest_id, home_last_id, away_last_id] if mid]
        if tactical_match_ids:
            tactical_results = await retrieve(
                query=f"{home_name} vs {away_name} tactical analysis",
                top_k=8,
                match_ids=tactical_match_ids,
                force_levels=["tactical_level"],
            )
            all_results.extend(tactical_results)

        # player_level: 关键球员画像
        h2h_players = extract_key_players(h2h_key_events, 5)
        home_players = extract_key_players(home_key_events, 5)
        away_players = extract_key_players(away_key_events, 5)
        player_ids = list(dict.fromkeys(h2h_players + home_players + away_players))

        if player_ids:
            player_results = await retrieve(
                query=f"{home_name} vs {away_name} key players",
                top_k=10,
                player_ids=player_ids,
                force_levels=["player_level"],
            )
            all_results.extend(player_results)

        segments_data = [
            {"text": r["text"][:200], "collection": r.get("collection", ""), "score": round(float(r.get("score", 0)), 3)}
            for r in all_results
        ]
        step_log = await push_step(
            state, node, "completed",
            _msg(node, "completed", lang, n=len(all_results)),
            data={"segments": segments_data},
        )
        return {"step_log": step_log, "rag_context": all_results}

    except Exception as e:
        await set_task_status(state["task_id"], "failed")
        step_log = await push_step(state, node, "error", str(e))
        return {"step_log": step_log, "rag_context": [], "error": str(e)}


@llm_retry(max_retries=3)
async def _call_matchup_analysis(
    ar: dict, rag_context: list[dict], language: str = "en"
) -> str:
    llm = get_deepseek_llm()
    teams = ar.get("teams", {})
    home_id = ar.get("home_id")
    away_id = ar.get("away_id")
    home_name = teams.get(home_id, "Home")
    away_name = teams.get(away_id, "Away")
    h2h = ar.get("h2h_matches", [])

    h2h_text = "\n".join(
        f"  {m['match_date']}: {m['home_name']} {m['home_score']}-{m['away_score']} {m['away_name']} "
        f"(Formations: {m['home_formation']} vs {m['away_formation']})"
        for m in h2h[:5]
    ) or ("  No direct head-to-head records found." if language != "zh" else "  无直接对抗记录。")

    context_text = "\n\n".join(
        f"[Source {i+1}] {r['text']}" for i, r in enumerate(rag_context[:20])
    ) or ("No tactical context available." if language != "zh" else "无战术背景数据。")

    if language == "zh":
        prompt = f"""你是一位专业足球球探和战术分析师。请生成一份详细的赛前情报报告。

对阵：{home_name}（主队）vs {away_name}（客队）

历史交锋记录（最近 5 场）：
{h2h_text}

来自知识库的战术背景：
{context_text}

请用 Markdown 格式生成详细情报报告，包含以下部分：
## 对阵概述
## {home_name} 战术画像
## {away_name} 战术画像
## 关键战术对抗
## 历史交锋分析
## 情报总结
"""
# 不要包含任何开场白、客套语或免责声明，直接从 ## 对阵概述 开始。
# 请具体分析，仅引用上述数据。如适用请标注来源 [来源 N]。
    else:
        prompt = f"""You are an expert football scout and tactical analyst. Generate a pre-match intelligence report.

MATCHUP: {home_name} (Home) vs {away_name} (Away)

HEAD-TO-HEAD HISTORY (last 5):
{h2h_text}

TACTICAL CONTEXT FROM KNOWLEDGE BASE:
{context_text}

Generate a detailed intelligence report in Markdown with sections:
## Matchup Overview
## {home_name} Tactical Profile
## {away_name} Tactical Profile
## Key Tactical Battles
## Head-to-Head Analysis
## Intelligence Summary

"""
# Be specific. Only use data from above. Cite [Source N] when referencing context.
# Do NOT include any preamble, greeting, or disclaimer. Start directly with ## Matchup Overview.

    response = await llm.ainvoke([HumanMessage(content=prompt)])
    return response.content


async def matchup_analysis(state: AnalysisState) -> dict:
    node = "matchup_analysis"
    lang = state.get("language", "en")
    try:
        step_log = await push_step(state, node, "started", _msg(node, "started", lang))
        ar = state.get("analysis_result") or {}
        rag_context = state.get("rag_context") or []

        analysis_text = await _call_matchup_analysis(ar, rag_context, lang)

        step_log = await push_step(state, node, "completed", _msg(node, "completed", lang))
        existing = dict(ar)
        existing["analysis_text"] = analysis_text
        return {"step_log": step_log, "analysis_result": existing}

    except Exception as e:
        await set_task_status(state["task_id"], "failed")
        step_log = await push_step(state, node, "error", str(e))
        return {"step_log": step_log, "error": str(e)}


async def intelligence_report(state: AnalysisState) -> dict:
    node = "intelligence_report"
    lang = state.get("language", "en")
    try:
        step_log = await push_step(state, node, "started", _msg(node, "started", lang))

        ar = state.get("analysis_result") or {}
        teams = ar.get("teams", {})
        home_id = ar.get("home_id")
        away_id = ar.get("away_id")
        analysis_text = ar.get("analysis_text", "Analysis unavailable.")
        home_name = teams.get(home_id, "Home")
        away_name = teams.get(away_id, "Away")

        if lang == "zh":
            report = f"""# 赛前情报报告
## {home_name} vs {away_name}

---

{analysis_text}

---
*由 AloFootMind 生成 — 基于 DeepSeek +RAG（BAAI/bge-m3 + Milvus）*
"""
        else:
            report = f"""# Pre-Match Intelligence Report
## {home_name} vs {away_name}

---

{analysis_text}

---
*Generated by AloFootMind — powered by DeepSeek +RAG (BAAI/bge-m3 + Milvus)*
"""

        from sqlalchemy import text
        from app.db.postgres import AsyncSessionLocal
        async with AsyncSessionLocal() as session:
            await session.execute(
                text("""
                    INSERT INTO analysis_reports (report_type, home_team_id, away_team_id, report_markdown, user_id)
                    VALUES ('pre_match', :h, :a, :md, :uid)
                """),
                {"h": home_id, "a": away_id, "md": report, "uid": state.get("user_id")},
            )
            await session.commit()

        await set_task_result(state["task_id"], report)
        step_log = await push_step(state, node, "completed", "Intelligence report saved.")
        return {"step_log": step_log, "report_markdown": report}

    except Exception as e:
        await set_task_status(state["task_id"], "failed")
        step_log = await push_step(state, node, "error", str(e))
        return {"step_log": step_log, "error": str(e)}


def _route_on_error(state: AnalysisState) -> str:
    return "error" if state.get("error") else "continue"


def build_pre_match_graph() -> StateGraph:
    graph = StateGraph(AnalysisState)
    graph.add_node("fetch_team_history", fetch_team_history)
    graph.add_node("rag_retrieval", rag_retrieval)
    graph.add_node("matchup_analysis", matchup_analysis)
    graph.add_node("intelligence_report", intelligence_report)

    graph.set_entry_point("fetch_team_history")
    graph.add_conditional_edges("fetch_team_history", _route_on_error, {"continue": "rag_retrieval", "error": END})
    graph.add_conditional_edges("rag_retrieval", _route_on_error, {"continue": "matchup_analysis", "error": END})
    graph.add_conditional_edges("matchup_analysis", _route_on_error, {"continue": "intelligence_report", "error": END})
    graph.add_edge("intelligence_report", END)

    return graph.compile()
