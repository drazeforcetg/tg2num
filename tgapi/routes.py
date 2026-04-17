import asyncio
import time
import uuid
import json
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Query, Header
from fastapi.responses import JSONResponse, Response
from .keyManager import getApiKey
from .limiter import checkAndConsumeLimit, getSystemEnabled
from .queue import enqueueRequest, getQueueStats
from .responseBuilder import buildSuccess, buildError, errorMap
from .requestLogger import logRequest

router = APIRouter()

def nowIso() -> str:
    return datetime.now(timezone.utc).isoformat()

def prettyJson(data: dict, code: int) -> Response:
    return Response(
        content=json.dumps(data, indent=2),
        status_code=code,
        media_type="application/json",
    )

@router.get("/lookup")
async def lookup(
    q: str = Query(...),
    apiKey: Optional[str] = Query(None, alias="api_key"),
    xApiKey: Optional[str] = Header(None, alias="x-api-key"),
):
    resolvedKey = xApiKey or apiKey
    requestId = str(uuid.uuid4())
    startTime = time.monotonic()
    searchedTime = nowIso()

    ms = lambda: int((time.monotonic() - startTime) * 1000)

    if not resolvedKey:
        return prettyJson(buildError(requestId, q, searchedTime, ms(), 401, "invalid_api_key", errorMap["invalid_api_key"][1]), 401)

    systemOn = await getSystemEnabled()
    if not systemOn:
        return prettyJson(buildError(requestId, q, searchedTime, ms(), 503, "system_disabled", errorMap["system_disabled"][1]), 503)

    keyDoc = await getApiKey(resolvedKey)
    if not keyDoc:
        return prettyJson(buildError(requestId, q, searchedTime, ms(), 401, "invalid_api_key", errorMap["invalid_api_key"][1]), 401)

    allowed, reason, remainingToday, totalUsed = await checkAndConsumeLimit(keyDoc)
    if not allowed:
        statusCode, msg = errorMap[reason]
        await logRequest(requestId, keyDoc["key"], q, "error", errorType=reason, processingTimeMs=ms())
        return prettyJson(buildError(requestId, q, searchedTime, ms(), statusCode, reason, msg), statusCode)

    queueStart = time.monotonic()
    try:
        responseFuture = await enqueueRequest(q, requestId)
        workerResult = await asyncio.wait_for(responseFuture, timeout=35)
    except asyncio.TimeoutError:
        await logRequest(requestId, keyDoc["key"], q, "error", errorType="timeout", processingTimeMs=ms())
        return prettyJson(buildError(requestId, q, searchedTime, ms(), 504, "timeout", errorMap["timeout"][1], remainingToday, totalUsed), 504)

    queueTimeMs = int((time.monotonic() - queueStart) * 1000)
    result = workerResult.get("result", {})
    workerId = workerResult.get("workerId", "unknown")

    if result.get("timeout"):
        await logRequest(requestId, keyDoc["key"], q, "error", errorType="timeout", processingTimeMs=ms())
        return prettyJson(buildError(requestId, q, searchedTime, ms(), 504, "timeout", errorMap["timeout"][1], remainingToday, totalUsed), 504)

    if not result.get("found") or not result.get("data"):
        await logRequest(requestId, keyDoc["key"], q, "error", errorType="not_found", processingTimeMs=ms())
        return prettyJson(buildError(requestId, q, searchedTime, ms(), 404, "not_found", errorMap["not_found"][1], remainingToday, totalUsed), 404)

    data = result["data"]
    response = buildSuccess(
        requestId=requestId,
        query=q,
        searchedTime=searchedTime,
        processingTimeMs=ms(),
        data=data,
        remainingToday=remainingToday,
        totalUsed=totalUsed,
        queueTimeMs=queueTimeMs,
        workerId=workerId,
        cacheHit=False,
    )
    await logRequest(requestId, keyDoc["key"], q, "success", responseData=data, processingTimeMs=ms())
    return prettyJson(response, 200)

@router.get("/health")
async def health():
    return prettyJson({"status": "ok", "queue": getQueueStats()}, 200)