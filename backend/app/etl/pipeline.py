"""
ETL pipeline orchestrator.

Execution order per match:
  step_parse → step_embed → step_postgres → step_redis_invalidate
"""
import asyncio
import json
import logging
from collections import defaultdict

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.redis_client import get_redis
from app.etl import ingestion_log as ilog
from app.etl.milvus_writer import (
    write_match_summaries,
    write_player_profiles,
    write_tactical_segments,
    write_team_tactical_profiles,
    write_team_tactical_profiles,
)
from app.etl.parser import (
    iter_all_matches,
    load_events,
    load_lineups,
    parse_events_aggregated,
    parse_lineup_records,
    parse_match_record,
    slice_possession_sequences,
)
from app.etl.text_generator import (
    aggregate_player_season_stats,
    aggregate_team_tactical_stats,
    aggregate_team_tactical_stats,
    generate_match_summary,
    generate_player_profile,
    generate_tactical_segment_text,
    generate_team_tactical_profile,
    generate_team_tactical_profile,
)

logger = logging.getLogger(__name__)


async def _write_postgres(session: AsyncSession, parsed: dict) -> None:
    from sqlalchemy import text

    mr = parsed["match_record"]
    await session.execute(
        text("""
            INSERT INTO competitions (competition_id, competition_name, country_name, competition_gender, competition_youth, competition_international)
            VALUES (:cid, :cname, :country, 'male', false, false)
            ON CONFLICT (competition_id) DO NOTHING
        """),
        {"cid": mr["competition_id"], "cname": mr["competition_name"], "country": mr["country_name"]},
    )

    await session.execute(
        text("""
            INSERT INTO seasons (season_id, season_name, competition_id)
            VALUES (:sid, :sname, :cid)
            ON CONFLICT (competition_id, season_id) DO NOTHING
        """),
        {"sid": mr["season_id"], "sname": mr["season_name"], "cid": mr["competition_id"]},
    )

    for team_id, team_name in [
        (mr["home_team_id"], mr["home_team_name"]),
        (mr["away_team_id"], mr["away_team_name"]),
    ]:
        await session.execute(
            text("""
                INSERT INTO teams (team_id, team_name, team_gender)
                VALUES (:tid, :tname, 'male')
                ON CONFLICT (team_id) DO NOTHING
            """),
            {"tid": team_id, "tname": team_name},
        )

    for lu in parsed["lineup_records"]:
        await session.execute(
            text("""
                INSERT INTO players (player_id, player_name, country_name)
                VALUES (:pid, :pname, :country)
                ON CONFLICT (player_id) DO NOTHING
            """),
            {"pid": lu["player_id"], "pname": lu["player_name"], "country": lu.get("country_name")},
        )

    season_row = await session.execute(
        text("SELECT id FROM seasons WHERE competition_id=:cid AND season_id=:sid"),
        {"cid": mr["competition_id"], "sid": mr["season_id"]},
    )
    season_pk = season_row.scalar_one()

    await session.execute(
        text("""
            INSERT INTO matches (
                match_id, match_date, kick_off,
                home_team_id, away_team_id, home_score, away_score,
                match_week, stadium_name, season_id,
                home_formation, away_formation, home_manager, away_manager
            ) VALUES (
                :mid, :mdate, :ko,
                :htm, :atm, :hs, :as_,
                :mw, :stad, :sid,
                :hf, :af, :hm, :am
            )
            ON CONFLICT (match_id) DO UPDATE
                SET home_formation = EXCLUDED.home_formation,
                    away_formation = EXCLUDED.away_formation
        """),
        {
            "mid": mr["match_id"], "mdate": mr["match_date"], "ko": mr.get("kick_off"),
            "htm": mr["home_team_id"], "atm": mr["away_team_id"],
            "hs": mr["home_score"], "as_": mr["away_score"],
            "mw": mr.get("match_week"), "stad": mr.get("stadium_name"),
            "sid": season_pk,
            "hf": mr.get("home_formation"), "af": mr.get("away_formation"),
            "hm": mr.get("home_manager"), "am": mr.get("away_manager"),
        },
    )

    for lu in parsed["lineup_records"]:
        await session.execute(
            text("""
                INSERT INTO match_lineups (match_id, team_id, player_id, position_name, jersey_number)
                VALUES (:mid, :tid, :pid, :pos, :jn)
                ON CONFLICT (match_id, player_id) DO NOTHING
            """),
            {
                "mid": mr["match_id"], "tid": lu["team_id"], "pid": lu["player_id"],
                "pos": lu.get("position_name"), "jn": lu.get("jersey_number"),
            },
        )

    ea = parsed["events_aggregated"]
    await session.execute(
        text("""
            INSERT INTO events_aggregated (
                match_id, total_events, total_possessions,
                home_shots, away_shots, home_shots_on_target, away_shots_on_target,
                home_passes, away_passes, home_fouls, away_fouls, key_events_json
            ) VALUES (
                :mid, :te, :tp,
                :hs, :as_, :hst, :ast_,
                :hp, :ap, :hf, :af, :kej
            )
            ON CONFLICT (match_id) DO UPDATE
                SET total_events = EXCLUDED.total_events,
                    total_possessions = EXCLUDED.total_possessions,
                    home_shots = EXCLUDED.home_shots,
                    away_shots = EXCLUDED.away_shots,
                    home_shots_on_target = EXCLUDED.home_shots_on_target,
                    away_shots_on_target = EXCLUDED.away_shots_on_target,
                    home_passes = EXCLUDED.home_passes,
                    away_passes = EXCLUDED.away_passes,
                    home_fouls = EXCLUDED.home_fouls,
                    away_fouls = EXCLUDED.away_fouls,
                    key_events_json = EXCLUDED.key_events_json
        """),
        {
            "mid": ea["match_id"], "te": ea["total_events"], "tp": ea["total_possessions"],
            "hs": ea["home_shots"], "as_": ea["away_shots"],
            "hst": ea["home_shots_on_target"], "ast_": ea["away_shots_on_target"],
            "hp": ea["home_passes"], "ap": ea["away_passes"],
            "hf": ea["home_fouls"], "af": ea["away_fouls"],
            "kej": ea["key_events_json"],
        },
    )

    await session.commit()


async def ingest_match(
    session: AsyncSession,
    comp_entry: dict,
    match: dict,
    dry_run: bool = False,
) -> None:
    match_id = match["match_id"]
    logger.info(f"[ETL] Processing match_id={match_id}")

    await ilog.upsert_log(session, match_id)

    if await ilog.is_fully_done(session, match_id):
        logger.info(f"[ETL] match_id={match_id} already fully ingested, skipping.")
        return

    parsed: dict = {}

    # ── step_parse ──────────────────────────────────────────────────────────
    if not await ilog.is_step_done(session, match_id, "step_parse"):
        try:
            events = load_events(match_id)
            mr = parse_match_record(comp_entry, match, events=events)
            lineups_data = load_lineups(match_id)
            lineup_records = parse_lineup_records(match_id, lineups_data)
            events_agg = parse_events_aggregated(
                match_id, mr["home_team_id"], mr["away_team_id"], events
            )
            parsed = {
                "match_record": mr,
                "events": events,
                "lineup_records": lineup_records,
                "events_aggregated": events_agg,
            }
            if not dry_run:
                await ilog.mark_step(session, match_id, "step_parse", "done")
        except Exception as e:
            await ilog.mark_step(session, match_id, "step_parse", "failed", str(e))
            logger.error(f"[ETL] step_parse failed for match_id={match_id}: {e}")
            return
    else:
        events = load_events(match_id)
        mr = parse_match_record(comp_entry, match, events=events)
        lineups_data = load_lineups(match_id)
        lineup_records = parse_lineup_records(match_id, lineups_data)
        events_agg = parse_events_aggregated(
            match_id, mr["home_team_id"], mr["away_team_id"], events
        )
        parsed = {
            "match_record": mr,
            "events": events,
            "lineup_records": lineup_records,
            "events_aggregated": events_agg,
        }

    mr = parsed["match_record"]
    events = parsed["events"]

    # ── step_embed ──────────────────────────────────────────────────────────
    if not await ilog.is_step_done(session, match_id, "step_embed"):
        try:
            if not dry_run:
                key_events = json.loads(events_agg["key_events_json"])

                summary_text = await generate_match_summary(mr, key_events)
                write_match_summaries([{
                    "match_id": match_id,
                    "competition_id": mr["competition_id"],
                    "season_id": mr["season_id"],
                    "home_team_id": mr["home_team_id"],
                    "away_team_id": mr["away_team_id"],
                    "text": summary_text,
                }])

                possession_seqs = slice_possession_sequences(events)
                tactical_entries = []
                for idx, seq in enumerate(possession_seqs):
                    team_id = (seq[0].get("team") or {}).get("id", 0) if seq else 0
                    text = generate_tactical_segment_text(
                        seq,
                        mr["home_team_name"],
                        mr["away_team_name"],
                        mr["home_team_id"],
                    )
                    if text:
                        tactical_entries.append({
                            "match_id": match_id,
                            "competition_id": mr["competition_id"],
                            "season_id": mr["season_id"],
                            "team_id": team_id,
                            "possession_index": idx,
                            "text": text,
                        })
                if tactical_entries:
                    write_tactical_segments(tactical_entries)

                await ilog.mark_step(session, match_id, "step_embed", "done")
        except Exception as e:
            await session.rollback()
            await ilog.mark_step(session, match_id, "step_embed", "failed", str(e))
            logger.error(f"[ETL] step_embed failed for match_id={match_id}: {e}")

    # ── step_postgres ────────────────────────────────────────────────────────
    if not await ilog.is_step_done(session, match_id, "step_postgres"):
        try:
            if not dry_run:
                await _write_postgres(session, parsed)
                await ilog.mark_step(session, match_id, "step_postgres", "done")
        except Exception as e:
            await session.rollback()
            await ilog.mark_step(session, match_id, "step_postgres", "failed", str(e))
            logger.error(f"[ETL] step_postgres failed for match_id={match_id}: {e}")
            return

    # ── step_redis_invalidate ────────────────────────────────────────────────
    if not await ilog.is_step_done(session, match_id, "step_redis_invalidate"):
        try:
            if not dry_run:
                redis = await get_redis()
                pattern = f"rag:*:match:{match_id}:*"
                keys = await redis.keys(pattern)
                if keys:
                    await redis.delete(*keys)
                comp_pattern = f"api:competitions:{mr['competition_id']}:*"
                comp_keys = await redis.keys(comp_pattern)
                if comp_keys:
                    await redis.delete(*comp_keys)
                await ilog.mark_step(session, match_id, "step_redis_invalidate", "done")
        except Exception as e:
            await ilog.mark_step(session, match_id, "step_redis_invalidate", "failed", str(e))
            logger.error(f"[ETL] step_redis_invalidate failed for match_id={match_id}: {e}")
            return

    logger.info(f"[ETL] match_id={match_id} ingestion complete.")


async def ingest_player_profiles(
    session: AsyncSession,
    competition_id: int,
    season_id: int,
    competition_name: str,
    season_name: str,
    dry_run: bool = False,
) -> None:
    """Generate and embed player profiles for a season after all matches are ingested."""
    from sqlalchemy import text as sqla_text

    result = await session.execute(
        sqla_text("""
            SELECT ml.player_id, p.player_name, ml.team_id, t.team_name
            FROM match_lineups ml
            JOIN matches m ON ml.match_id = m.match_id
            JOIN seasons s ON m.season_id = s.id
            JOIN players p ON ml.player_id = p.player_id
            JOIN teams t ON ml.team_id = t.team_id
            WHERE s.competition_id = :cid AND s.season_id = :sid
            GROUP BY ml.player_id, p.player_name, ml.team_id, t.team_name
        """),
        {"cid": competition_id, "sid": season_id},
    )
    players = result.mappings().all()

    result2 = await session.execute(
        sqla_text("""
            SELECT m.match_id
            FROM matches m
            JOIN seasons s ON m.season_id = s.id
            WHERE s.competition_id = :cid AND s.season_id = :sid
        """),
        {"cid": competition_id, "sid": season_id},
    )
    match_ids = [r[0] for r in result2]

    matches_events: list[tuple[int, list[dict]]] = []
    for mid in match_ids:
        evs = load_events(mid)
        matches_events.append((mid, evs))

    from pymilvus import Collection as _Collection
    _pcol = _Collection("player_profiles")
    _pcol.load()

    from pymilvus import Collection as _Collection
    _pcol = _Collection("player_profiles")
    _pcol.load()

    for player_row in players:
        pid = player_row["player_id"]

        # Skip if already exists in Milvus for this season
        existing = _pcol.query(
            expr=f"player_id == {pid} && season_id == {season_id}",
            output_fields=["player_id"],
            limit=1,
        )
        if existing:
            logger.debug(f"[ETL] Player profile already exists for pid={pid}, skipping.")
            continue


        # Skip if already exists in Milvus for this season
        existing = _pcol.query(
            expr=f"player_id == {pid} && season_id == {season_id}",
            output_fields=["player_id"],
            limit=1,
        )
        if existing:
            logger.debug(f"[ETL] Player profile already exists for pid={pid}, skipping.")
            continue

        stats = aggregate_player_season_stats(pid, matches_events)
        if stats["appearances"] == 0:
            continue

        if not dry_run:
            profile_text = await generate_player_profile(
                player_name=player_row["player_name"],
                player_id=pid,
                team_name=player_row["team_name"],
                competition_name=competition_name,
                season_name=season_name,
                stats=stats,
            )
            write_player_profiles([{
                "player_id": pid,
                "competition_id": competition_id,
                "season_id": season_id,
                "team_id": player_row["team_id"],
                "text": profile_text,
            }])
            logger.info(f"[ETL] Player profile written: {player_row['player_name']} (pid={pid})")


async def ingest_team_tactical_profiles(
    session: AsyncSession,
    competition_id: int,
    season_id: int,
    competition_name: str,
    season_name: str,
    dry_run: bool = False,
) -> None:
    """Generate and embed team tactical profiles for a season after all matches are ingested."""
    from sqlalchemy import text as sqla_text

    result = await session.execute(
        sqla_text("""
            SELECT DISTINCT
                CASE WHEN m.home_team_id = t.team_id THEN m.home_team_id
                     ELSE m.away_team_id END AS team_id,
                t.team_name
            FROM matches m
            JOIN seasons s ON m.season_id = s.id
            JOIN teams t ON t.team_id = m.home_team_id OR t.team_id = m.away_team_id
            WHERE s.competition_id = :cid AND s.season_id = :sid
        """),
        {"cid": competition_id, "sid": season_id},
    )
    teams = result.mappings().all()

    result2 = await session.execute(
        sqla_text("""
            SELECT m.match_id
            FROM matches m
            JOIN seasons s ON m.season_id = s.id
            WHERE s.competition_id = :cid AND s.season_id = :sid
        """),
        {"cid": competition_id, "sid": season_id},
    )
    match_ids = [r[0] for r in result2]

    matches_events: list[tuple[int, list[dict]]] = []
    for mid in match_ids:
        evs = load_events(mid)
        matches_events.append((mid, evs))

    from pymilvus import Collection as _Collection
    _tcol = _Collection("team_tactical_profiles")
    _tcol.load()

    for team_row in teams:
        tid = team_row["team_id"]
        team_name = team_row["team_name"]

        # Skip if already exists in Milvus for this season
        existing = _tcol.query(
            expr=f"team_id == {tid} && season_id == {season_id}",
            output_fields=["team_id"],
            limit=1,
        )
        if existing:
            logger.debug(f"[ETL] Team tactical profile already exists for tid={tid}, skipping.")
            continue

        stats = aggregate_team_tactical_stats(tid, matches_events)
        if stats["total_possessions"] == 0:
            logger.warning(f"[ETL] No possession data for team_id={tid}, skipping.")
            continue

        if not dry_run:
            profile_text = await generate_team_tactical_profile(
                team_name=team_name,
                team_id=tid,
                competition_name=competition_name,
                season_name=season_name,
                stats=stats,
            )
            write_team_tactical_profiles([{
                "team_id": tid,
                "competition_id": competition_id,
                "season_id": season_id,
                "text": profile_text,
            }])
            logger.info(f"[ETL] Team tactical profile written: {team_name} (tid={tid})")


async def ingest_team_tactical_profiles(
    session: AsyncSession,
    competition_id: int,
    season_id: int,
    competition_name: str,
    season_name: str,
    dry_run: bool = False,
) -> None:
    """Generate and embed team tactical profiles for a season after all matches are ingested."""
    from sqlalchemy import text as sqla_text

    result = await session.execute(
        sqla_text("""
            SELECT DISTINCT
                CASE WHEN m.home_team_id = t.team_id THEN m.home_team_id
                     ELSE m.away_team_id END AS team_id,
                t.team_name
            FROM matches m
            JOIN seasons s ON m.season_id = s.id
            JOIN teams t ON t.team_id = m.home_team_id OR t.team_id = m.away_team_id
            WHERE s.competition_id = :cid AND s.season_id = :sid
        """),
        {"cid": competition_id, "sid": season_id},
    )
    teams = result.mappings().all()

    result2 = await session.execute(
        sqla_text("""
            SELECT m.match_id
            FROM matches m
            JOIN seasons s ON m.season_id = s.id
            WHERE s.competition_id = :cid AND s.season_id = :sid
        """),
        {"cid": competition_id, "sid": season_id},
    )
    match_ids = [r[0] for r in result2]

    matches_events: list[tuple[int, list[dict]]] = []
    for mid in match_ids:
        evs = load_events(mid)
        matches_events.append((mid, evs))

    from pymilvus import Collection as _Collection
    _tcol = _Collection("team_tactical_profiles")
    _tcol.load()

    for team_row in teams:
        tid = team_row["team_id"]
        team_name = team_row["team_name"]

        # Skip if already exists in Milvus for this season
        existing = _tcol.query(
            expr=f"team_id == {tid} && season_id == {season_id}",
            output_fields=["team_id"],
            limit=1,
        )
        if existing:
            logger.debug(f"[ETL] Team tactical profile already exists for tid={tid}, skipping.")
            continue

        stats = aggregate_team_tactical_stats(tid, matches_events)
        if stats["total_possessions"] == 0:
            logger.warning(f"[ETL] No possession data for team_id={tid}, skipping.")
            continue

        if not dry_run:
            profile_text = await generate_team_tactical_profile(
                team_name=team_name,
                team_id=tid,
                competition_name=competition_name,
                season_name=season_name,
                stats=stats,
            )
            write_team_tactical_profiles([{
                "team_id": tid,
                "competition_id": competition_id,
                "season_id": season_id,
                "text": profile_text,
            }])
            logger.info(f"[ETL] Team tactical profile written: {team_name} (tid={tid})")
