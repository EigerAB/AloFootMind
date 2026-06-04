#!/usr/bin/env python3
"""
Reset ETL state before a full re-ingestion.
- Drop and recreate Milvus collections
- Truncate ingestion_log table
- Optional: truncate player_profiles Milvus collection (no ingestion_log tracking)
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import dotenv
dotenv.load_dotenv(Path(__file__).parent.parent / ".env")

import asyncio

from app.core.config import settings
from app.db.milvus_init import COLLECTIONS, INDEX_PARAMS, BGE_M3_DIM
from app.db.postgres import AsyncSessionLocal, init_db
from sqlalchemy import text
from pymilvus import (
    Collection,
    CollectionSchema,
    connections,
    utility,
)

MILVUS_COLLECTIONS = list(COLLECTIONS.keys())


def _drop_and_recreate_milvus() -> None:
    connections.connect(
        alias="default",
        host=settings.MILVUS_HOST,
        port=settings.MILVUS_PORT,
    )

    for name in MILVUS_COLLECTIONS:
        if utility.has_collection(name):
            utility.drop_collection(name)
            print(f"[milvus] Dropped collection '{name}'")
        else:
            print(f"[milvus] Collection '{name}' did not exist")

        schema = CollectionSchema(
            fields=COLLECTIONS[name]["fields"],
            description=COLLECTIONS[name]["description"],
            enable_dynamic_field=False,
        )
        collection = Collection(name=name, schema=schema)
        for field_name, idx_params in INDEX_PARAMS.items():
            collection.create_index(field_name=field_name, index_params=idx_params)
        collection.load()
        print(f"[milvus] Created and loaded collection '{name}'")

    connections.disconnect("default")


async def _truncate_ingestion_log() -> None:
    await init_db()
    async with AsyncSessionLocal() as session:
        result = await session.execute(text("SELECT COUNT(*) FROM ingestion_log"))
        count = result.scalar()
        await session.execute(text("TRUNCATE TABLE ingestion_log"))
        await session.commit()
        print(f"[postgres] Truncated ingestion_log ({count} rows removed)")


async def main() -> None:
    print("=== ETL Reset ===")
    _drop_and_recreate_milvus()
    await _truncate_ingestion_log()
    print("=== Reset complete. Run 'python scripts/ingest.py' to re-ingest. ===")


if __name__ == "__main__":
    asyncio.run(main())
