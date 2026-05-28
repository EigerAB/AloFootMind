"""PreMatch Sub-graph: fetch_team_history → rag_retrieval → matchup_analysis → intelligence_report."""
from __future__ import annotations

import logging

from langchain_core.messages import HumanMessage
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


async def fetch_team_history(state: AnalysisState) -> dict:
    node = "fetch_team_history"
    try:
        step_log = await push_step(state, node, "started", "Loading team historical data...")

        from sqlalchemy import text
        from app.db.postgres import AsyncSessionLocal

        team_ids = state.get("team_ids") or []
        if len(team_ids) < 2:
            return {"step_log": await push_step(state, node, "failed", "Need 2 team IDs."),
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

        step_log = await push_step(
            state, node, "completed",
            f"Found {len(h2h_matches)} head-to-head matches for "
            f"{teams.get(home_id, home_id)} vs {teams.get(away_id, away_id)}."
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
        step_log = await push_step(state, node, "failed", str(e))
        return {"step_log": step_log, "error": str(e)}


async def rag_retrieval(state: AnalysisState) -> dict:
    node = "rag_retrieval"
    try:
        step_log = await push_step(state, node, "started", "Searching tactical knowledge base for both teams...")

        ar = state.get("analysis_result") or {}
        teams = ar.get("teams", {})
        home_id = ar.get("home_id")
        away_id = ar.get("away_id")
        home_name = teams.get(home_id, "Home team")
        away_name = teams.get(away_id, "Away team")

        home_ctx = await retrieve(
            query=f"{home_name} attacking tactics and formation",
            top_k=4, team_id=home_id, force_levels=["tactical_level"],
        )
        away_ctx = await retrieve(
            query=f"{away_name} defensive tactics and formation",
            top_k=4, team_id=away_id, force_levels=["tactical_level"],
        )

        rag_context = home_ctx + away_ctx
        step_log = await push_step(
            state, node, "completed",
            f"Retrieved {len(rag_context)} tactical segments."
        )
        return {"step_log": step_log, "rag_context": rag_context}

    except Exception as e:
        step_log = await push_step(state, node, "failed", str(e))
        return {"step_log": step_log, "rag_context": [], "error": str(e)}


@llm_retry(max_retries=3)
async def _call_matchup_analysis(
    ar: dict, rag_context: list[dict]
) -> str:
    llm = _deepseek()
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
    ) or "  No direct head-to-head records found."

    context_text = "\n\n".join(
        f"[Source {i+1}] {r['text']}" for i, r in enumerate(rag_context[:8])
    ) or "No tactical context available."

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

Be specific. Only use data from above. Cite [Source N] when referencing context."""

    response = await llm.ainvoke([HumanMessage(content=prompt)])
    return response.content


async def matchup_analysis(state: AnalysisState) -> dict:
    node = "matchup_analysis"
    try:
        step_log = await push_step(state, node, "started", "Running GPT-4o matchup analysis...")
        ar = state.get("analysis_result") or {}
        rag_context = state.get("rag_context") or []

        analysis_text = await _call_matchup_analysis(ar, rag_context)

        step_log = await push_step(state, node, "completed", "Matchup analysis complete.")
        existing = dict(ar)
        existing["analysis_text"] = analysis_text
        return {"step_log": step_log, "analysis_result": existing}

    except Exception as e:
        step_log = await push_step(state, node, "failed", str(e))
        return {"step_log": step_log, "error": str(e)}


async def intelligence_report(state: AnalysisState) -> dict:
    node = "intelligence_report"
    try:
        step_log = await push_step(state, node, "started", "Generating intelligence report...")

        ar = state.get("analysis_result") or {}
        teams = ar.get("teams", {})
        home_id = ar.get("home_id")
        away_id = ar.get("away_id")
        analysis_text = ar.get("analysis_text", "Analysis unavailable.")

        report = f"""# Pre-Match Intelligence Report
## {teams.get(home_id, 'Home')} vs {teams.get(away_id, 'Away')}

---

{analysis_text}

---
*Generated by AloFootMind — powered by GPT-4o + RAG (BAAI/bge-m3 + Milvus)*
"""

        from sqlalchemy import text
        from app.db.postgres import AsyncSessionLocal
        async with AsyncSessionLocal() as session:
            await session.execute(
                text("""
                    INSERT INTO analysis_reports (report_type, home_team_id, away_team_id, report_markdown)
                    VALUES ('pre_match', :h, :a, :md)
                """),
                {"h": home_id, "a": away_id, "md": report},
            )
            await session.commit()

        await set_task_result(state["task_id"], report)
        step_log = await push_step(state, node, "completed", "Intelligence report saved.")
        return {"step_log": step_log, "report_markdown": report}

    except Exception as e:
        step_log = await push_step(state, node, "failed", str(e))
        return {"step_log": step_log, "error": str(e)}


def build_pre_match_graph() -> StateGraph:
    graph = StateGraph(AnalysisState)
    graph.add_node("fetch_team_history", fetch_team_history)
    graph.add_node("rag_retrieval", rag_retrieval)
    graph.add_node("matchup_analysis", matchup_analysis)
    graph.add_node("intelligence_report", intelligence_report)

    graph.set_entry_point("fetch_team_history")
    graph.add_edge("fetch_team_history", "rag_retrieval")
    graph.add_edge("rag_retrieval", "matchup_analysis")
    graph.add_edge("matchup_analysis", "intelligence_report")
    graph.add_edge("intelligence_report", END)

    return graph.compile()
