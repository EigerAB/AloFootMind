#!/usr/bin/env python3
"""
ETL CLI entry point.

Usage:
  python scripts/ingest.py --competition_id 2
  python scripts/ingest.py --competition_id 2 --dry-run
"""
import argparse
import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import dotenv
dotenv.load_dotenv(Path(__file__).parent.parent / ".env")

from app.db.postgres import AsyncSessionLocal, init_db
from app.db.milvus_client import connect_milvus
from app.db.milvus_init import init_milvus_collections
from app.etl.parser import iter_all_matches, load_competitions
from app.etl.pipeline import ingest_match, ingest_player_profiles

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger("ingest")


async def main(competition_id: int | None, season_id: int | None, dry_run: bool) -> None:
    logger.info("Initialising database...")
    await init_db()
    logger.info("Ensuring Milvus collections exist...")
    from app.core.config import settings
    init_milvus_collections(settings.MILVUS_HOST, settings.MILVUS_PORT)
    logger.info("Reconnecting to Milvus for ETL session...")
    connect_milvus()

    competitions = load_competitions(competition_id)
    logger.info(f"Found {len(competitions)} competition/season entries to process.")

    processed_seasons: set[tuple[int, int]] = set()

    async with AsyncSessionLocal() as session:
        for comp_entry, match in iter_all_matches(competition_id, season_id):
            if dry_run:
                logger.info(
                    f"[dry-run] Would ingest match_id={match['match_id']} "
                    f"({comp_entry['competition_name']} {comp_entry['season_name']})"
                )
            else:
                await ingest_match(session, comp_entry, match, dry_run=dry_run)

            key = (comp_entry["competition_id"], comp_entry["season_id"])
            processed_seasons.add(key)

        if not dry_run:
            for cid, sid in processed_seasons:
                comp_list = load_competitions(cid)
                comp_entry_for_season = next(
                    (c for c in comp_list if c["season_id"] == sid), None
                )
                if comp_entry_for_season:
                    logger.info(
                        f"Generating player profiles for competition={cid} season={sid}..."
                    )
                    await ingest_player_profiles(
                        session=session,
                        competition_id=cid,
                        season_id=sid,
                        competition_name=comp_entry_for_season["competition_name"],
                        season_name=comp_entry_for_season["season_name"],
                        dry_run=dry_run,
                    )

    logger.info("ETL complete.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AloFootMind ETL ingestion script")
    parser.add_argument(
        "--competition_id",
        type=int,
        default=None,
        help="StatsBomb competition_id to ingest (omit for all)",
    )
    parser.add_argument(
        "--season_id",
        type=int,
        default=None,
        help="StatsBomb season_id to ingest (omit for all seasons in competition)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse only, do not write to any storage",
    )
    args = parser.parse_args()
    logger.info(f"Args: {args}")
    asyncio.run(main(args.competition_id, args.season_id, args.dry_run))
