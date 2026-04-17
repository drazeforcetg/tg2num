import asyncio
from datetime import datetime, timezone
from typing import Optional
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import IndexModel, ASCENDING, DESCENDING
from loguru import logger
import os

_client: Optional[AsyncIOMotorClient] = None

def getDb():
    return _client["tgapi"]

async def connectDb():
    global _client
    uri = os.getenv("MONGO_URI", "mongodb://localhost:27017")
    _client = AsyncIOMotorClient(uri)
    db = getDb()
    await db["apiKeys"].create_indexes([
        IndexModel([("key", ASCENDING)], unique=True),
        IndexModel([("createdAt", DESCENDING)]),
    ])
    await db["requestLogs"].create_indexes([
        IndexModel([("requestId", ASCENDING)], unique=True),
        IndexModel([("apiKey", ASCENDING)]),
        IndexModel([("createdAt", DESCENDING)]),
        IndexModel([("createdAt", ASCENDING)], expireAfterSeconds=2592000),
    ])
    await db["usageStats"].create_indexes([
        IndexModel([("apiKey", ASCENDING), ("date", ASCENDING)], unique=True),
    ])
    logger.info("MongoDB connected")

async def disconnectDb():
    if _client:
        _client.close()