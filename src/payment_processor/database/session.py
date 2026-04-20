from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from payment_processor.core.config import settings

_engine = create_async_engine(
    url=settings.db.url,
    echo=settings.environment == "local",
    pool_pre_ping=True,
)

_session_factory = async_sessionmaker(
    bind=_engine,
    expire_on_commit=False,
)


async def get_session() -> AsyncIterator[AsyncSession]:
    async with _session_factory() as session:
        yield session


async def dispose_engine() -> None:
    await _engine.dispose()
