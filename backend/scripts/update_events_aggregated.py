#!/usr/bin/env python3
"""
Update events_aggregated records in PostgreSQL using demo-data events files.
Only updates the stats columns, does NOT touch Milvus embeddings.
"""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import dotenv
dotenv.load_dotenv(Path(__file__).parent.parent / ".env")

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import settings
from app.etl.parser import parse_events_aggregated

DATA_DIR = Path(__file__).parent.parent.parent / "demo-data"


async def main() -> None:
    engine = create_async_engine(settings.DB_URL)

    async with engine.begin() as conn:
        # Get all matches with their team IDs
        result = await conn.execute(
            text("SELECT match_id, home_team_id, away_team_id FROM matches")
        )
        matches = result.mappings().all()

        updated = 0
        skipped = 0

        for row in matches:
            mid = row["match_id"]
            home_id = row["home_team_id"]
            away_id = row["away_team_id"]

            events_path = DATA_DIR / "events" / f"{mid}.json"
            if not events_path.exists():
                print(f"[SKIP] No events file for match_id={mid}")
                skipped += 1
                continue

            with open(events_path, encoding="utf-8") as f:
                events = json.load(f)

            parsed = parse_events_aggregated(mid, home_id, away_id, events)

            await conn.execute(
                text("""
                    UPDATE events_aggregated
                    SET total_events = :te,
                        total_possessions = :tp,
                        home_shots = :hs,
                        away_shots = :as_,
                        home_shots_on_target = :hst,
                        away_shots_on_target = :ast_,
                        home_passes = :hp,
                        away_passes = :ap,
                        home_fouls = :hf,
                        away_fouls = :af,
                        key_events_json = :kej
                    WHERE match_id = :mid
                """),
                {
                    "te": parsed["total_events"],
                    "tp": parsed["total_possessions"],
                    "hs": parsed["home_shots"],
                    "as_": parsed["away_shots"],
                    "hst": parsed["home_shots_on_target"],
                    "ast_": parsed["away_shots_on_target"],
                    "hp": parsed["home_passes"],
                    "ap": parsed["away_passes"],
                    "hf": parsed["home_fouls"],
                    "af": parsed["away_fouls"],
                    "kej": parsed["key_events_json"],
                    "mid": mid,
                },
            )
            print(f"[OK] match_id={mid}: shots={parsed['home_shots']}/{parsed['away_shots']}, passes={parsed['home_passes']}/{parsed['away_passes']}, key_events={len(json.loads(parsed['key_events_json']))}")
            updated += 1

        print(f"\nDone: {updated} updated, {skipped} skipped")


if __name__ == "__main__":
    asyncio.run(main())
