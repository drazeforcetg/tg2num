from datetime import datetime, timezone
from typing import Optional, Any, Dict
from .database import getDb

async def logRequest(
    requestId: str,
    apiKey: str,
    query: str,
    status: str,
    responseData: Optional[Dict] = None,
    errorType: Optional[str] = None,
    processingTimeMs: Optional[int] = None,
):
    await getDb()["requestLogs"].insert_one({
        "requestId": requestId,
        "apiKey": apiKey,
        "query": query,
        "status": status,
        "responseData": responseData,
        "errorType": errorType,
        "processingTimeMs": processingTimeMs,
        "createdAt": datetime.now(timezone.utc),
    })

async def getRecentLogs(limit: int = 20) -> list:
    cursor = getDb()["requestLogs"].find(
        {},
        {"_id": 0, "requestId": 1, "apiKey": 1, "query": 1, "status": 1, "errorType": 1, "processingTimeMs": 1, "createdAt": 1}
    ).sort("createdAt", -1).limit(limit)
    return await cursor.to_list(length=limit)

async def getAnalytics() -> Dict[str, Any]:
    db = getDb()
    totalRequests = await db["requestLogs"].count_documents({})
    totalSuccess = await db["requestLogs"].count_documents({"status": "success"})
    totalErrors = await db["requestLogs"].count_documents({"status": "error"})
    return {
        "totalRequests": totalRequests,
        "totalSuccess": totalSuccess,
        "totalErrors": totalErrors,
    }