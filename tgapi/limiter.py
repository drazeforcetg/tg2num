import asyncio
from datetime import date, datetime, timezone
from typing import Tuple, Dict, Any
import redis.asyncio as aioredis
from loguru import logger
from .database import getDb
import os

_redis: aioredis.Redis = None

async def connectRedis():
    global _redis
    url = os.getenv("REDIS_URL", "redis://localhost:6379")
    _redis = aioredis.from_url(url, decode_responses=True)
    logger.info("Redis connected")

async def disconnectRedis():
    if _redis:
        await _redis.close()

def getRedis() -> aioredis.Redis:
    return _redis

async def checkAndConsumeLimit(keyDoc: Dict[str, Any]) -> Tuple[bool, str, int, int]:
    keyHash = keyDoc["key"]
    today = date.today().isoformat()
    dailyKey = f"usage:daily:{keyHash}:{today}"
    rateKey = f"usage:rate:{keyHash}"
    r = getRedis()

    pipe = r.pipeline()
    pipe.incr(rateKey)
    pipe.expire(rateKey, 60)
    pipe.incr(dailyKey)
    pipe.expire(dailyKey, 86400)
    results = await pipe.execute()

    rateCount = results[0]
    dailyCount = results[2]

    if rateCount > keyDoc.get("rateLimitPerMinute", 10):
        await pipe.decr(rateKey)
        await pipe.decr(dailyKey)
        await pipe.execute()
        return False, "rate_limit_exceeded", 0, 0

    if dailyCount > keyDoc.get("dailyLimit", 100):
        await r.decr(dailyKey)
        return False, "daily_limit_exceeded", 0, 0

    totalUsed = keyDoc.get("totalUsed", 0) + 1
    if totalUsed > keyDoc.get("totalLimit", 10000):
        await r.decr(dailyKey)
        return False, "daily_limit_exceeded", 0, 0

    await getDb()["apiKeys"].update_one(
        {"key": keyHash},
        {"$inc": {"totalUsed": 1}, "$set": {"lastUsedAt": datetime.now(timezone.utc)}},
    )
    await getDb()["usageStats"].update_one(
        {"apiKey": keyHash, "date": today},
        {"$inc": {"count": 1}},
        upsert=True,
    )

    remainingToday = max(0, keyDoc.get("dailyLimit", 100) - dailyCount)
    totalUsedFinal = keyDoc.get("totalUsed", 0) + 1
    return True, "ok", remainingToday, totalUsedFinal

async def getDailyUsage(keyHash: str) -> int:
    today = date.today().isoformat()
    val = await getRedis().get(f"usage:daily:{keyHash}:{today}")
    return int(val) if val else 0

async def getSystemEnabled() -> bool:
    val = await getRedis().get("system:enabled")
    return val != "0"

async def setSystemEnabled(enabled: bool):
    await getRedis().set("system:enabled", "1" if enabled else "0")