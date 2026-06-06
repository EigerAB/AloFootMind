import json
from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.postgres import get_db
from app.db.redis_client import get_redis

router = APIRouter(prefix="/api", tags=["competitions"])


@router.get("/competitions")
async def list_competitions(session: AsyncSession = Depends(get_db)):
    redis = await get_redis()
    cache_key = "api:competitions:all"
    cached = await redis.get(cache_key)
    if cached:
        return json.loads(cached)

    result = await session.execute(
        text("""
            SELECT c.competition_id, c.competition_name, c.country_name,
                   s.season_id, s.season_name
            FROM competitions c
            JOIN seasons s ON s.competition_id = c.competition_id
            ORDER BY c.competition_name, s.season_name DESC
        """)
    )
    rows = [dict(r) for r in result.mappings()]
    await redis.set(cache_key, json.dumps(rows), ex=3600)
    return rows


@router.get("/teams")
async def list_teams(
    q: str | None = None,
    session: AsyncSession = Depends(get_db),
):
    if q:
        result = await session.execute(
            text("SELECT team_id, team_name FROM teams WHERE team_name ILIKE :q ORDER BY team_name LIMIT 50"),
            {"q": f"%{q}%"},
        )
    else:
        result = await session.execute(
            text("SELECT team_id, team_name FROM teams ORDER BY team_name LIMIT 200")
        )
    return [dict(r) for r in result.mappings()]


@router.get("/teams/hierarchy")
async def teams_hierarchy(session: AsyncSession = Depends(get_db)):
    """Return competitions as parent nodes with participating teams as leaf nodes."""
    result = await session.execute(
        text("""
            SELECT DISTINCT c.competition_id, c.competition_name, t.team_id, t.team_name
            FROM competitions c
            JOIN seasons s ON s.competition_id = c.competition_id
            JOIN matches m ON m.season_id = s.id
            JOIN teams t ON t.team_id = m.home_team_id OR t.team_id = m.away_team_id
            ORDER BY c.competition_name, t.team_name
        """)
    )
    rows = [dict(r) for r in result.mappings()]

    competitions: dict[int, dict] = {}
    for r in rows:
        cid = r["competition_id"]
        if cid not in competitions:
            competitions[cid] = {
                "competition_id": cid,
                "competition_name": r["competition_name"],
                "teams": [],
            }
        competitions[cid]["teams"].append(
            {"team_id": r["team_id"], "team_name": r["team_name"]}
        )

    return list(competitions.values())
