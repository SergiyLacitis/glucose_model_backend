from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI

from config import settings
from database import db_helper


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await db_helper.dispose()


app = FastAPI(
    title=settings.general.title,
    description=settings.general.description,
    lifespan=lifespan,
)


if __name__ == "__main__":
    uvicorn.run(
        app,
        host=settings.general.host,
        port=settings.general.port,
        log_level=settings.general.log_level,
    )
