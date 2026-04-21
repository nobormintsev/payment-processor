from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from payment_processor.core.exception_handlers import register_exception_handlers
from payment_processor.database.session import dispose_engine
from payment_processor.payments.router import router as payments_router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    yield
    await dispose_engine()


app = FastAPI(
    title="Payment Processor",
    lifespan=lifespan,
)
register_exception_handlers(app)
app.include_router(payments_router, prefix="/api/v1")
