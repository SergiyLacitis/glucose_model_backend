import uvicorn
from fastapi import FastAPI

from config import settings

app = FastAPI(title=settings.general.title, description=settings.general.description)


if __name__ == "__main__":
    uvicorn.run(
        app,
        host=settings.general.host,
        port=settings.general.port,
        log_level=settings.general.log_level,
    )
