import asyncio
import json
import uuid
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.graph import run_analysis
from app.core.security import require_role
from app.db.models import User
from app.db.postgres import get_db
from app.db.redis_client import get_redis

router = APIRouter(prefix="/api/matches", tags=["matches"])


class MatchListRequest(BaseModel):
    competition_id: Optional[int] = None
    season_id: Optional[int] = None
    team_id: Optional[int] = None
    limit: int = 50
    offset: int = 0


@router.post("")
async def list_matches(
    body: MatchListRequest,
    session: AsyncSession = Depends(get_db),
):
    filters = ["1=1"]
    params: dict = {}

    if body.competition_id is not None:
        filters.append("s.competition_id = :competition_id")
        params["competition_id"] = body.competition_id
    if body.season_id is not None:
        filters.append("s.season_id = :season_id")
        params["season_id"] = body.season_id
    if body.team_id is not None:
        filters.append("(m.home_team_id = :team_id OR m.away_team_id = :team_id)")
        params["team_id"] = body.team_id

    where = " AND ".join(filters)

    count_result = await session.execute(
        text(f"""
            SELECT COUNT(*) AS total
            FROM matches m
            JOIN teams ht ON m.home_team_id = ht.team_id
            JOIN teams at ON m.away_team_id = at.team_id
            JOIN seasons s ON m.season_id = s.id
            JOIN competitions c ON s.competition_id = c.competition_id
            WHERE {where}
        """),
        params,
    )
    total = count_result.scalar_one() or 0

    params["limit"] = body.limit
    params["offset"] = body.offset
    result = await session.execute(
        text(f"""
            SELECT m.match_id, m.match_date, m.home_score, m.away_score,
                   m.match_week, m.home_formation, m.away_formation,
                   ht.team_name AS home_team_name,
                   at.team_name AS away_team_name,
                   c.competition_name, s.season_name,
                   EXISTS (
                       SELECT 1 FROM analysis_reports ar
                       WHERE ar.match_id = m.match_id AND ar.report_type = 'post_match'
                   ) AS has_report
            FROM matches m
            JOIN teams ht ON m.home_team_id = ht.team_id
            JOIN teams at ON m.away_team_id = at.team_id
            JOIN seasons s ON m.season_id = s.id
            JOIN competitions c ON s.competition_id = c.competition_id
            WHERE {where}
            ORDER BY m.match_date DESC
            LIMIT :limit OFFSET :offset
        """),
        params,
    )
    items = [dict(r) for r in result.mappings()]
    return {"items": items, "total": total}


@router.get("/{match_id}")
async def get_match(match_id: int, session: AsyncSession = Depends(get_db)):
    result = await session.execute(
        text("""
            SELECT m.match_id, m.match_date, m.home_score, m.away_score,
                   m.match_week, m.stadium_name, m.home_formation, m.away_formation,
                   m.home_manager, m.away_manager,
                   ht.team_id AS home_team_id, ht.team_name AS home_team_name,
                   at.team_id AS away_team_id, at.team_name AS away_team_name,
                   c.competition_name, s.season_name,
                   ea.home_shots, ea.away_shots,
                   ea.home_shots_on_target, ea.away_shots_on_target,
                   ea.home_passes, ea.away_passes,
                   ea.home_fouls, ea.away_fouls,
                   ea.key_events_json
            FROM matches m
            JOIN teams ht ON m.home_team_id = ht.team_id
            JOIN teams at ON m.away_team_id = at.team_id
            JOIN seasons s ON m.season_id = s.id
            JOIN competitions c ON s.competition_id = c.competition_id
            LEFT JOIN events_aggregated ea ON m.match_id = ea.match_id
            WHERE m.match_id = :mid
        """),
        {"mid": match_id},
    )
    row = result.mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="Match not found")

    match_data = dict(row)
    if match_data.get("key_events_json"):
        match_data["key_events"] = json.loads(match_data.pop("key_events_json"))

    lineup_result = await session.execute(
        text("""
            SELECT p.player_id, p.player_name, ml.team_id,
                   ml.position_name, ml.jersey_number
            FROM match_lineups ml
            JOIN players p ON ml.player_id = p.player_id
            WHERE ml.match_id = :mid
            ORDER BY ml.team_id, ml.jersey_number
        """),
        {"mid": match_id},
    )
    match_data["lineups"] = [dict(r) for r in lineup_result.mappings()]
    return match_data


class AnalyzeRequest(BaseModel):
    language: str = "en"


@router.post("/{match_id}/analyze")
async def trigger_analysis(
    match_id: int,
    body: AnalyzeRequest,
    background_tasks: BackgroundTasks,
    user: User = Depends(require_role("full")),
    session: AsyncSession = Depends(get_db),
):
    row = await session.execute(
        text("SELECT match_id FROM matches WHERE match_id = :mid"),
        {"mid": match_id},
    )
    if not row.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Match not found")

    report_row = await session.execute(
        text("SELECT id FROM analysis_reports WHERE match_id = :mid AND report_type = 'post_match' AND language = :lang LIMIT 1"),
        {"mid": match_id, "lang": body.language},
    )
    if report_row.scalar_one_or_none():
        return {"match_id": match_id, "status": "already_done", "task_id": None}

    task_id = str(uuid.uuid4())
    redis = await get_redis()
    await redis.set(f"task:{task_id}:status", "pending", ex=3600)

    background_tasks.add_task(
        run_analysis,
        {"task_id": task_id, "request_type": "post_match", "match_id": match_id, "language": body.language, "user_id": user.id},
    )
    return {"match_id": match_id, "task_id": task_id, "status": "pending"}


@router.get("/{match_id}/report")
async def get_report(match_id: int, language: str = "en", session: AsyncSession = Depends(get_db)):
    result = await session.execute(
        text("""
            SELECT report_markdown, created_at
            FROM analysis_reports
            WHERE match_id = :mid AND report_type = 'post_match' AND language = :lang
            ORDER BY created_at DESC LIMIT 1
        """),
        {"mid": match_id, "lang": language},
    )
    row = result.mappings().first()
    if not row:
        raise HTTPException(status_code=202, detail="Report not yet available")
    return {"match_id": match_id, "report_markdown": row["report_markdown"],
            "created_at": str(row["created_at"])}
