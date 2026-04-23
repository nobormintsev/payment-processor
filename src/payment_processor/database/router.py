from fastapi import APIRouter
from sqlalchemy import text

from payment_processor.database.session import engine

router = APIRouter(
    prefix="/database",
    tags=["database"],
)


@router.get("/health", include_in_schema=False)
async def health() -> dict[str, str]:
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))

    return {"status": "ok"}
