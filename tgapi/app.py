from contextlib import asynccontextmanager
from fastapi import FastAPI
from loguru import logger
from .database import connectDb, disconnectDb
from .limiter import connectRedis, disconnectRedis
from .telegramClient import startClient, stopClient
from .queue import workerPool
from .routes import router

@asynccontextmanager
async def lifespan(app: FastAPI):
    await connectDb()
    await connectRedis()
    await startClient()
    await workerPool.start()
    logger.info("All services started")
    yield
    await workerPool.stop()
    await stopClient()
    await disconnectRedis()
    await disconnectDb()
    logger.info("All services stopped")

app = FastAPI(lifespan=lifespan, title="TG Lookup API", docs_url=None, redoc_url=None)
app.include_router(router, prefix="/api/v1")