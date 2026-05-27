"""ingestion_log: idempotent step tracking for ETL pipeline."""
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

STEPS = ("step_parse", "step_embed", "step_postgres", "step_redis_invalidate")
STATUS_DONE = "done"
STATUS_PENDING = "pending"
STATUS_FAILED = "failed"


async def get_log(session: AsyncSession, match_id: int) -> dict | None:
    result = await session.execute(
        text("SELECT * FROM ingestion_log WHERE match_id = :mid"),
        {"mid": match_id},
    )
    row = result.mappings().first()
    return dict(row) if row else None


async def upsert_log(session: AsyncSession, match_id: int) -> None:
    """Insert a fresh log row if it doesn't already exist."""
    await session.execute(
        text("""
            INSERT INTO ingestion_log (match_id)
            VALUES (:mid)
            ON CONFLICT (match_id) DO NOTHING
        """),
        {"mid": match_id},
    )
    await session.commit()


async def mark_step(
    session: AsyncSession,
    match_id: int,
    step: str,
    status: str,
    error: str | None = None,
) -> None:
    assert step in STEPS, f"Unknown step: {step}"
    assert status in (STATUS_DONE, STATUS_PENDING, STATUS_FAILED)
    await session.execute(
        text(f"""
            UPDATE ingestion_log
            SET {step} = :status,
                last_error = :error,
                updated_at = now()
            WHERE match_id = :mid
        """),
        {"status": status, "error": error, "mid": match_id},
    )
    await session.commit()


async def is_step_done(session: AsyncSession, match_id: int, step: str) -> bool:
    log = await get_log(session, match_id)
    if log is None:
        return False
    return log.get(step) == STATUS_DONE


async def is_fully_done(session: AsyncSession, match_id: int) -> bool:
    log = await get_log(session, match_id)
    if log is None:
        return False
    return all(log.get(s) == STATUS_DONE for s in STEPS)
