from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from sqlmodel import SQLModel

from config import settings
from database import db_helper
from routers import api_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with db_helper.engine.begin() as conn:
        import models.user

        await conn.run_sync(SQLModel.metadata.create_all)
    yield
    await db_helper.dispose()


app = FastAPI(
    title=settings.general.title,
    description=settings.general.description,
    lifespan=lifespan,
)

app.include_router(api_router)


if __name__ == "__main__":
    uvicorn.run(
        app,
        host=settings.general.host,
        port=settings.general.port,
        log_level=settings.general.log_level,
    )
