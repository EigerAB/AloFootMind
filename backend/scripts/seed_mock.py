"""Mock seed script – inserts demo data without StatsBomb files.

Usage:
    python -m scripts.seed_mock
    # or from project root:
    python backend/scripts/seed_mock.py
"""
from __future__ import annotations

import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "../.env"))

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.db.models import (
    Competition, EventsAggregated, Match, MatchLineup, Player, Season, Team,
)

# ---------------------------------------------------------------------------
# Seed data
# ---------------------------------------------------------------------------

COMPETITION = dict(
    competition_id=9001,
    competition_name="Mock La Liga",
    country_name="Spain",
    competition_gender="male",
    competition_youth=False,
    competition_international=False,
)

SEASON = dict(season_id=2024, season_name="2023/24", competition_id=9001)

TEAMS = [
    dict(team_id=9001, team_name="Real Madrid", country_name="Spain"),
    dict(team_id=9002, team_name="Barcelona", country_name="Spain"),
    dict(team_id=9003, team_name="Atlético Madrid", country_name="Spain"),
    dict(team_id=9004, team_name="Sevilla", country_name="Spain"),
]

PLAYERS = [
    # Real Madrid
    dict(player_id=9001, player_name="Thibaut Courtois", country_name="Belgium"),
    dict(player_id=9002, player_name="Dani Carvajal", country_name="Spain"),
    dict(player_id=9003, player_name="Éder Militão", country_name="Brazil"),
    dict(player_id=9004, player_name="Aurélien Tchouaméni", country_name="France"),
    dict(player_id=9005, player_name="Luka Modrić", country_name="Croatia"),
    dict(player_id=9006, player_name="Jude Bellingham", country_name="England"),
    dict(player_id=9007, player_name="Vinícius Jr.", country_name="Brazil"),
    # Barcelona
    dict(player_id=9011, player_name="Marc-André ter Stegen", country_name="Germany"),
    dict(player_id=9012, player_name="Jules Koundé", country_name="France"),
    dict(player_id=9013, player_name="Ronald Araújo", country_name="Uruguay"),
    dict(player_id=9014, player_name="Pedri", country_name="Spain"),
    dict(player_id=9015, player_name="Gavi", country_name="Spain"),
    dict(player_id=9016, player_name="Robert Lewandowski", country_name="Poland"),
    dict(player_id=9017, player_name="Raphinha", country_name="Brazil"),
    # Atlético Madrid
    dict(player_id=9021, player_name="Jan Oblak", country_name="Slovenia"),
    dict(player_id=9022, player_name="Nahuel Molina", country_name="Argentina"),
    dict(player_id=9023, player_name="José María Giménez", country_name="Uruguay"),
    dict(player_id=9024, player_name="Koke", country_name="Spain"),
    dict(player_id=9025, player_name="Antoine Griezmann", country_name="France"),
    dict(player_id=9026, player_name="Álvaro Morata", country_name="Spain"),
    # Sevilla
    dict(player_id=9031, player_name="Yassine Bounou", country_name="Morocco"),
    dict(player_id=9032, player_name="Jesús Navas", country_name="Spain"),
    dict(player_id=9033, player_name="Sergio Ramos", country_name="Spain"),
    dict(player_id=9034, player_name="Ivan Rakitić", country_name="Croatia"),
    dict(player_id=9035, player_name="Lucas Ocampos", country_name="Argentina"),
]

MATCHES = [
    dict(
        match_id=9001, match_date="2024-01-14", kick_off="21:00",
        home_team_id=9001, away_team_id=9002,
        home_score=2, away_score=1, match_week=20,
        stadium_name="Santiago Bernabéu",
        home_formation=4312, away_formation=4231,
        home_manager="Carlo Ancelotti", away_manager="Xavi Hernández",
        season_pk=None,  # filled at runtime
        stats=dict(
            home_shots=15, away_shots=9,
            home_shots_on_target=6, away_shots_on_target=3,
            home_passes=520, away_passes=610,
            home_fouls=12, away_fouls=14,
            key_events=[
                dict(type="Goal", team_id=9001, player="Jude Bellingham", minute=34, period=1),
                dict(type="Goal", team_id=9002, player="Robert Lewandowski", minute=58, period=2),
                dict(type="Goal", team_id=9001, player="Vinícius Jr.", minute=78, period=2),
            ],
        ),
        lineup={
            9001: [(9001,"GK",1),(9002,"RB",2),(9003,"CB",3),(9004,"CM",5),(9005,"CM",10),(9006,"AM",5),(9007,"LW",7)],
            9002: [(9011,"GK",1),(9012,"RB",23),(9013,"CB",4),(9014,"CM",8),(9015,"CM",6),(9016,"ST",9),(9017,"RW",11)],
        },
    ),
    dict(
        match_id=9002, match_date="2024-01-21", kick_off="17:00",
        home_team_id=9003, away_team_id=9004,
        home_score=1, away_score=0, match_week=21,
        stadium_name="Metropolitano",
        home_formation=4411, away_formation=4231,
        home_manager="Diego Simeone", away_manager="Quique Sánchez Flores",
        season_pk=None,
        stats=dict(
            home_shots=11, away_shots=7,
            home_shots_on_target=4, away_shots_on_target=2,
            home_passes=430, away_passes=380,
            home_fouls=16, away_fouls=10,
            key_events=[
                dict(type="Goal", team_id=9003, player="Antoine Griezmann", minute=62, period=2),
            ],
        ),
        lineup={
            9003: [(9021,"GK",1),(9022,"RB",16),(9023,"CB",2),(9024,"CM",6),(9025,"AM",8),(9026,"ST",9)],
            9004: [(9031,"GK",1),(9032,"RB",16),(9033,"CB",4),(9034,"CM",8),(9035,"RW",5)],
        },
    ),
    dict(
        match_id=9003, match_date="2024-02-04", kick_off="21:00",
        home_team_id=9002, away_team_id=9003,
        home_score=3, away_score=2, match_week=23,
        stadium_name="Camp Nou",
        home_formation=4231, away_formation=4411,
        home_manager="Xavi Hernández", away_manager="Diego Simeone",
        season_pk=None,
        stats=dict(
            home_shots=17, away_shots=11,
            home_shots_on_target=8, away_shots_on_target=5,
            home_passes=640, away_passes=490,
            home_fouls=9, away_fouls=17,
            key_events=[
                dict(type="Goal", team_id=9002, player="Robert Lewandowski", minute=12, period=1),
                dict(type="Goal", team_id=9003, player="Álvaro Morata", minute=29, period=1),
                dict(type="Goal", team_id=9002, player="Pedri", minute=51, period=2),
                dict(type="YellowCard", team_id=9003, player="Koke", minute=66, period=2),
                dict(type="Goal", team_id=9003, player="Antoine Griezmann", minute=71, period=2),
                dict(type="Goal", team_id=9002, player="Raphinha", minute=89, period=2),
            ],
        ),
        lineup={
            9002: [(9011,"GK",1),(9012,"RB",23),(9013,"CB",4),(9014,"CM",8),(9015,"CM",6),(9016,"ST",9),(9017,"RW",11)],
            9003: [(9021,"GK",1),(9022,"RB",16),(9023,"CB",2),(9024,"CM",6),(9025,"AM",8),(9026,"ST",9)],
        },
    ),
    dict(
        match_id=9004, match_date="2024-02-18", kick_off="19:00",
        home_team_id=9004, away_team_id=9001,
        home_score=0, away_score=3, match_week=25,
        stadium_name="Ramón Sánchez-Pizjuán",
        home_formation=4231, away_formation=4312,
        home_manager="Quique Sánchez Flores", away_manager="Carlo Ancelotti",
        season_pk=None,
        stats=dict(
            home_shots=6, away_shots=14,
            home_shots_on_target=1, away_shots_on_target=7,
            home_passes=350, away_passes=560,
            home_fouls=18, away_fouls=8,
            key_events=[
                dict(type="Goal", team_id=9001, player="Vinícius Jr.", minute=23, period=1),
                dict(type="Goal", team_id=9001, player="Jude Bellingham", minute=48, period=2),
                dict(type="Goal", team_id=9001, player="Luka Modrić", minute=83, period=2),
            ],
        ),
        lineup={
            9004: [(9031,"GK",1),(9032,"RB",16),(9033,"CB",4),(9034,"CM",8),(9035,"RW",5)],
            9001: [(9001,"GK",1),(9002,"RB",2),(9003,"CB",3),(9004,"CM",5),(9005,"CM",10),(9006,"AM",5),(9007,"LW",7)],
        },
    ),
    dict(
        match_id=9005, match_date="2024-03-10", kick_off="16:15",
        home_team_id=9001, away_team_id=9003,
        home_score=1, away_score=1, match_week=28,
        stadium_name="Santiago Bernabéu",
        home_formation=4312, away_formation=4411,
        home_manager="Carlo Ancelotti", away_manager="Diego Simeone",
        season_pk=None,
        stats=dict(
            home_shots=13, away_shots=8,
            home_shots_on_target=5, away_shots_on_target=3,
            home_passes=510, away_passes=420,
            home_fouls=11, away_fouls=19,
            key_events=[
                dict(type="Goal", team_id=9001, player="Vinícius Jr.", minute=37, period=1),
                dict(type="Goal", team_id=9003, player="Antoine Griezmann", minute=81, period=2),
            ],
        ),
        lineup={
            9001: [(9001,"GK",1),(9002,"RB",2),(9003,"CB",3),(9004,"CM",5),(9005,"CM",10),(9006,"AM",5),(9007,"LW",7)],
            9003: [(9021,"GK",1),(9022,"RB",16),(9023,"CB",2),(9024,"CM",6),(9025,"AM",8),(9026,"ST",9)],
        },
    ),
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def upsert(session: AsyncSession, model, pk_field: str, **values):
    obj = await session.get(model, values[pk_field])
    if obj is None:
        obj = model(**values)
        session.add(obj)
    return obj


async def seed(session: AsyncSession):
    print("📦 Seeding competition & season...")
    comp = await session.get(Competition, COMPETITION["competition_id"])
    if not comp:
        session.add(Competition(**COMPETITION))

    await session.flush()

    season_row = (await session.execute(
        text("SELECT id FROM seasons WHERE competition_id=:c AND season_id=:s"),
        {"c": SEASON["competition_id"], "s": SEASON["season_id"]},
    )).fetchone()
    if not season_row:
        s = Season(**SEASON)
        session.add(s)
        await session.flush()
        season_pk = s.id
    else:
        season_pk = season_row.id
    print(f"  season pk={season_pk}")

    print("👥 Seeding teams & players...")
    for t in TEAMS:
        if not await session.get(Team, t["team_id"]):
            session.add(Team(**t))
    for p in PLAYERS:
        if not await session.get(Player, p["player_id"]):
            session.add(Player(**p))
    await session.flush()

    print("⚽ Seeding matches, lineups & stats...")
    for m in MATCHES:
        stats = m.pop("stats")
        lineup = m.pop("lineup")
        m["season_pk"] = season_pk

        match_row = await session.get(Match, m["match_id"])
        if not match_row:
            match_row = Match(
                match_id=m["match_id"],
                match_date=m["match_date"],
                kick_off=m.get("kick_off"),
                home_team_id=m["home_team_id"],
                away_team_id=m["away_team_id"],
                home_score=m["home_score"],
                away_score=m["away_score"],
                match_week=m.get("match_week"),
                stadium_name=m.get("stadium_name"),
                season_id=season_pk,
                home_formation=m.get("home_formation"),
                away_formation=m.get("away_formation"),
                home_manager=m.get("home_manager"),
                away_manager=m.get("away_manager"),
            )
            session.add(match_row)
            await session.flush()

        # EventsAggregated
        existing_ev = await session.get(EventsAggregated, m["match_id"])
        if not existing_ev:
            session.add(EventsAggregated(
                match_id=m["match_id"],
                total_events=stats["home_passes"] + stats["away_passes"],
                total_possessions=0,
                home_shots=stats["home_shots"],
                away_shots=stats["away_shots"],
                home_shots_on_target=stats["home_shots_on_target"],
                away_shots_on_target=stats["away_shots_on_target"],
                home_passes=stats["home_passes"],
                away_passes=stats["away_passes"],
                home_fouls=stats["home_fouls"],
                away_fouls=stats["away_fouls"],
                key_events_json=json.dumps(stats["key_events"], ensure_ascii=False),
            ))

        # MatchLineup
        for team_id, players in lineup.items():
            for player_id, position, jersey in players:
                result = await session.execute(
                    text("SELECT id FROM match_lineups WHERE match_id=:m AND player_id=:p"),
                    {"m": m["match_id"], "p": player_id},
                )
                if not result.fetchone():
                    session.add(MatchLineup(
                        match_id=m["match_id"],
                        team_id=team_id,
                        player_id=player_id,
                        position_name=position,
                        jersey_number=jersey,
                    ))

    await session.commit()
    print("✅ Seed complete!")


async def main():
    engine = create_async_engine(settings.DB_URL, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        await seed(session)
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
