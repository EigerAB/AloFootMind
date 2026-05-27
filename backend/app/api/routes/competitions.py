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
