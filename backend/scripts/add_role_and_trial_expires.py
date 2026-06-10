"""Add role and trial_expires_at columns to users table."""
import asyncio
import sys
sys.path.insert(0, "/Users/yangkunhong/Desktop/Projects/2026/AloFootMind_copy/backend")

from sqlalchemy import text
from app.db.postgres import engine


async def main():
    async with engine.begin() as conn:
        await conn.execute(
            text("""
                ALTER TABLE users
                ADD COLUMN IF NOT EXISTS role VARCHAR(20) DEFAULT 'full',
                ADD COLUMN IF NOT EXISTS trial_expires_at TIMESTAMP
            """)
        )
    print("Columns role and trial_expires_at added successfully.")


if __name__ == "__main__":
    asyncio.run(main())
