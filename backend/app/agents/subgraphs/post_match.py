"""PostMatch Sub-graph: fetch_match_data → rag_retrieval → tactical_analysis → report_generation."""

from __future__ import annotations

import json
import logging
import textwrap

from langchain_openai import ChatOpenAI
from langgraph.graph import END, StateGraph

DEEPSEEK_BASE = "https://api.deepseek.com/v1"

from app.agents.state import AnalysisState
from app.agents.utils import llm_retry, push_step, set_task_result
from app.core.config import settings
from app.services.rag_service import retrieve

logger = logging.getLogger(__name__)


def _deepseek() -> ChatOpenAI:
    return ChatOpenAI(
        model="deepseek-chat",
        api_key=settings.DEEPSEEK_API_KEY,
        base_url=DEEPSEEK_BASE,
        temperature=0.3,
        max_tokens=2000,
    )


async def fetch_match_data(state: AnalysisState) -> dict:
    node = "fetch_match_data"
    try:
        step_log = await push_step(
            state, node, "started", "Fetching match data from database..."
        )

        from sqlalchemy import text
        from app.db.postgres import AsyncSessionLocal

        match_id = state["match_id"]
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                text(
                    """
                    SELECT m.match_id, m.match_date, m.home_score, m.away_score,
                           m.home_formation, m.away_formation,
                           m.home_manager, m.away_manager,
                           ht.team_name AS home_team_name,
                           at.team_name AS away_team_name,
                           ea.key_events_json,
                           ea.home_shots, ea.away_shots,
                           ea.home_shots_on_target, ea.away_shots_on_target,
                           ea.home_passes, ea.away_passes,
                           ea.home_fouls, ea.away_fouls,
                           ea.total_possessions,
                           c.competition_name, s.season_name
                    FROM matches m
                    JOIN teams ht ON m.home_team_id = ht.team_id
                    JOIN teams at ON m.away_team_id = at.team_id
                    LEFT JOIN events_aggregated ea ON m.match_id = ea.match_id
                    LEFT JOIN seasons s ON m.season_id = s.id
                    LEFT JOIN competitions c ON s.competition_id = c.competition_id
                    WHERE m.match_id = :mid
                """
                ),
                {"mid": match_id},
            )
            row = result.mappings().first()

        if not row:
            step_log = await push_step(
                state, node, "failed", f"Match {match_id} not found."
            )
            return {"step_log": step_log, "error": f"Match {match_id} not found"}

        match_data = dict(row)
        step_log = await push_step(
            state,
            node,
            "completed",
            f"Loaded match: {match_data['home_team_name']} {match_data['home_score']}-"
            f"{match_data['away_score']} {match_data['away_team_name']}",
        )
        return {"step_log": step_log, "analysis_result": {"match_data": match_data}}

    except Exception as e:
        step_log = await push_step(state, node, "failed", str(e))
        return {"step_log": step_log, "error": str(e)}


async def rag_retrieval(state: AnalysisState) -> dict:
    node = "rag_retrieval"
    try:
        step_log = await push_step(
            state, node, "started", "Searching tactical knowledge base..."
        )

        match_data = (state.get("analysis_result") or {}).get("match_data", {})
        query = (
            f"{match_data.get('home_team_name', '')} vs "
            f"{match_data.get('away_team_name', '')} tactical analysis"
        )

        results = await retrieve(
            query=query,
            top_k=5,
            match_id=state["match_id"],
            force_levels=["tactical_level", "match_level"],
        )

        step_log = await push_step(
            state,
            node,
            "completed",
            f"Retrieved {len(results)} relevant tactical segments.",
        )
        return {"step_log": step_log, "rag_context": results}

    except Exception as e:
        step_log = await push_step(state, node, "failed", str(e))
        return {"step_log": step_log, "rag_context": [], "error": str(e)}


@llm_retry(max_retries=3)
async def _call_tactical_analysis(
    match_data: dict, rag_context: list[dict], language: str = "en"
) -> str:
    llm = _deepseek()
    context_text = "\n\n".join(
        f"[Source {i+1}] {r['text']}" for i, r in enumerate(rag_context[:5])
    ) or ("No historical context available." if language != "zh" else "无历史背景数据。")

    key_events = json.loads(match_data.get("key_events_json") or "[]")
    goals_text = "\n".join(
        f"  {g['minute']}' {g.get('player','Unknown')} ({g['type']})"
        for g in key_events
        if g["type"] == "Goal"
    ) or ("  No goals." if language != "zh" else "  无进球。")

    if language == "zh":
        prompt = f"""
                    你是一位专业的足球战术分析师。请根据以下数据和背景对这场比赛进行分析。

                    比赛：{match_data.get('home_team_name')} {match_data.get('home_score')}-{match_data.get('away_score')} {match_data.get('away_team_name')}
                    日期：{match_data.get('match_date')} | 赛事：{match_data.get('competition_name')} {match_data.get('season_name')}
                    阵型：{match_data.get('home_team_name')}（{match_data.get('home_formation')}）vs {match_data.get('away_team_name')}（{match_data.get('away_formation')}）
                    教练：{match_data.get('home_manager')} vs {match_data.get('away_manager')}

                    数据统计：
                    - 射门：{match_data.get('home_shots', 0)}（射正：{match_data.get('home_shots_on_target', 0)}）vs {match_data.get('away_shots', 0)}（射正：{match_data.get('away_shots_on_target', 0)}）
                    - 传球：{match_data.get('home_passes', 0)} vs {match_data.get('away_passes', 0)}
                    - 犯规：{match_data.get('home_fouls', 0)} vs {match_data.get('away_fouls', 0)}
                    - 总控球次数：{match_data.get('total_possessions', 0)}

                    进球：
                    {goals_text}

                    战术背景（来自知识库）：
                    {context_text}

                    请用 Markdown 格式提供结构化战术分析，包含以下部分：
                    ## 比赛概述
                    ## 战术阵型与站位
                    ## 关键战术时刻
                    ## 球员亮点
                    ## 战术总结

                    请具体且具有分析性，仅引用上述数据中的事实。如适用请标注来源编号 [来源 N]。
                    不要包含任何开场白、客套语或免责声明，直接从 ## 比赛概述 开始。
                    """
    else:
        prompt = f"""
                    You are an expert football tactical analyst. Analyze this match using the data and context provided.

                    MATCH: {match_data.get('home_team_name')} {match_data.get('home_score')}-{match_data.get('away_score')} {match_data.get('away_team_name')}
                    Date: {match_data.get('match_date')} | Competition: {match_data.get('competition_name')} {match_data.get('season_name')}
                    Formations: {match_data.get('home_team_name')} ({match_data.get('home_formation')}) vs {match_data.get('away_team_name')} ({match_data.get('away_formation')})
                    Managers: {match_data.get('home_manager')} vs {match_data.get('away_manager')}

                    STATS:
                    - Shots: {match_data.get('home_shots', 0)} (on target: {match_data.get('home_shots_on_target', 0)}) vs {match_data.get('away_shots', 0)} (on target: {match_data.get('away_shots_on_target', 0)})
                    - Passes: {match_data.get('home_passes', 0)} vs {match_data.get('away_passes', 0)}
                    - Fouls: {match_data.get('home_fouls', 0)} vs {match_data.get('away_fouls', 0)}
                    - Total possessions: {match_data.get('total_possessions', 0)}

                    GOALS:
                    {goals_text}

                    TACTICAL CONTEXT (from knowledge base):
                    {context_text}

                    Provide a structured tactical analysis in Markdown with these sections:
                    ## Match Overview
                    ## Tactical Formations & Shape
                    ## Key Tactical Moments
                    ## Player Highlights
                    ## Tactical Verdict

                    Be specific and analytical. Only reference facts from the data above. Cite source numbers [Source N] where applicable.
                    Do NOT include any preamble, greeting, or disclaimer. Start directly with ## Match Overview.
                    """

    from langchain_core.messages import HumanMessage

    response = await llm.ainvoke([HumanMessage(content=prompt)])
    return response.content


async def tactical_analysis(state: AnalysisState) -> dict:
    node = "tactical_analysis"
    try:
        step_log = await push_step(
            state, node, "started", "Running GPT-4o tactical analysis..."
        )

        match_data = (state.get("analysis_result") or {}).get("match_data", {})
        rag_context = state.get("rag_context") or []
        language = state.get("language", "en")

        analysis_text = await _call_tactical_analysis(match_data, rag_context, language)

        step_log = await push_step(
            state, node, "completed", "Tactical analysis complete."
        )
        existing = dict(state.get("analysis_result") or {})
        existing["tactical_text"] = analysis_text
        return {"step_log": step_log, "analysis_result": existing}

    except Exception as e:
        step_log = await push_step(state, node, "failed", str(e))
        return {"step_log": step_log, "error": str(e)}


async def report_generation(state: AnalysisState) -> dict:
    node = "report_generation"
    try:
        step_log = await push_step(state, node, "started", "Generating final report...")

        ar = state.get("analysis_result") or {}
        match_data = ar.get("match_data", {})
        tactical_text = ar.get("tactical_text", "Analysis unavailable.")
        language = state.get("language", "en")

        if language == "zh":
            report = textwrap.dedent(f"""\
# 比赛分析报告
## {match_data.get('home_team_name', '主队')} {match_data.get('home_score', 0)} – {match_data.get('away_score', 0)} {match_data.get('away_team_name', '客队')}

**日期：** {match_data.get('match_date', 'N/A')} | **赛事：** {match_data.get('competition_name', '')} {match_data.get('season_name', '')}

---

{tactical_text}

---
*由 AloFootMind 生成 — 基于 GPT-4o + RAG（BAAI/bge-m3 + Milvus）*
""").strip()
        else:
            report = textwrap.dedent(f"""\
# Match Analysis Report
## {match_data.get('home_team_name', 'Home')} {match_data.get('home_score', 0)} – {match_data.get('away_score', 0)} {match_data.get('away_team_name', 'Away')}

**Date:** {match_data.get('match_date', 'N/A')} | **Competition:** {match_data.get('competition_name', '')} {match_data.get('season_name', '')}

---

{tactical_text}

---
*Generated by AloFootMind — powered by GPT-4o + RAG (BAAI/bge-m3 + Milvus)*
""").strip()

        from sqlalchemy import text
        from app.db.postgres import AsyncSessionLocal

        async with AsyncSessionLocal() as session:
            await session.execute(
                text(
                    """
                    INSERT INTO analysis_reports (match_id, report_type, report_markdown, language)
                    VALUES (:mid, 'post_match', :md, :lang)
                    ON CONFLICT DO NOTHING
                """
                ),
                {"mid": state["match_id"], "md": report, "lang": language},
            )
            await session.commit()

        await set_task_result(state["task_id"], report)
        step_log = await push_step(
            state, node, "completed", "Report saved successfully."
        )
        return {"step_log": step_log, "report_markdown": report}

    except Exception as e:
        step_log = await push_step(state, node, "failed", str(e))
        return {"step_log": step_log, "error": str(e)}


def build_post_match_graph() -> StateGraph:
    graph = StateGraph(AnalysisState)
    graph.add_node("fetch_match_data", fetch_match_data)
    graph.add_node("rag_retrieval", rag_retrieval)
    graph.add_node("tactical_analysis", tactical_analysis)
    graph.add_node("report_generation", report_generation)

    graph.set_entry_point("fetch_match_data")
    graph.add_edge("fetch_match_data", "rag_retrieval")
    graph.add_edge("rag_retrieval", "tactical_analysis")
    graph.add_edge("tactical_analysis", "report_generation")
    graph.add_edge("report_generation", END)

    return graph.compile()
