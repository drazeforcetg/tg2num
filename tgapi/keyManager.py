import secrets
import hashlib
import string
from datetime import datetime, timezone, date
from typing import Optional, Dict, Any
from .database import getDb

_alphanum = string.ascii_letters + string.digits

def _randomSegment(length: int) -> str:
    return ''.join(secrets.choice(_alphanum) for _ in range(length))

def generateRawKey() -> str:
    return f"drazeX-{_randomSegment(6)}-{_randomSegment(6)}"

def hashKey(rawKey: str) -> str:
    return hashlib.sha256(rawKey.encode()).hexdigest()

async def generateApiKey(
    label: str = "",
    dailyLimit: int = 100,
    totalLimit: int = 10000,
    rateLimitPerMinute: int = 10,
) -> Dict[str, Any]:
    rawKey = generateRawKey()
    keyHash = hashKey(rawKey)
    doc = {
        "key": keyHash,
        "label": label,
        "dailyLimit": dailyLimit,
        "totalLimit": totalLimit,
        "rateLimitPerMinute": rateLimitPerMinute,
        "totalUsed": 0,
        "isActive": True,
        "createdAt": datetime.now(timezone.utc),
        "lastUsedAt": None,
    }
    await getDb()["apiKeys"].insert_one(doc)
    return {"rawKey": rawKey, "keyHash": keyHash, "label": label}

async def getApiKey(rawKey: str) -> Optional[Dict[str, Any]]:
    keyHash = hashKey(rawKey)
    return await getDb()["apiKeys"].find_one({"key": keyHash, "isActive": True})

async def revokeApiKey(keyHash: str) -> bool:
    result = await getDb()["apiKeys"].update_one(
        {"key": keyHash}, {"$set": {"isActive": False}}
    )
    return result.modified_count > 0

async def rotateApiKey(oldKeyHash: str) -> Optional[Dict[str, Any]]:
    existing = await getDb()["apiKeys"].find_one({"key": oldKeyHash})
    if not existing:
        return None
    newRaw = generateRawKey()
    newHash = hashKey(newRaw)
    await getDb()["apiKeys"].update_one(
        {"key": oldKeyHash},
        {"$set": {"key": newHash, "isActive": True}},
    )
    return {"rawKey": newRaw, "keyHash": newHash}

async def updateKeyLimits(keyHash: str, dailyLimit: int = None, totalLimit: int = None):
    update = {}
    if dailyLimit is not None:
        update["dailyLimit"] = dailyLimit
    if totalLimit is not None:
        update["totalLimit"] = totalLimit
    if update:
        await getDb()["apiKeys"].update_one({"key": keyHash}, {"$set": update})

async def resetKeyUsage(keyHash: str):
    await getDb()["usageStats"].delete_many({"apiKey": keyHash})
    await getDb()["apiKeys"].update_one({"key": keyHash}, {"$set": {"totalUsed": 0}})

async def listAllKeys() -> list:
    cursor = getDb()["apiKeys"].find(
        {},
        {"_id": 0, "key": 1, "label": 1, "isActive": 1, "totalUsed": 1, "dailyLimit": 1, "totalLimit": 1, "createdAt": 1}
    ).sort("createdAt", -1)
    return await cursor.to_list(length=200)