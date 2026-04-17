from typing import Optional, Any, Dict

def buildSuccess(
    requestId, query, searchedTime, processingTimeMs,
    data, remainingToday, totalUsed, queueTimeMs, workerId, cacheHit=False,
) -> Dict[str, Any]:
    countryCode = data.get("countryCode", "").strip().lstrip("+")
    phone = data.get("phone", "").strip()
    return {
        "status": "success",
        "statusCode": 200,
        "meta": {
            "requestId": requestId,
            "query": query,
            "searchedTime": searchedTime,
            "processingTimeMs": processingTimeMs,
        },
        "data": {
            "telegramId": data.get("telegramId"),
            "countryCode": f"+{countryCode}" if countryCode else "",
            "phone": phone,
            "country": data.get("country"),
        },
        "usage": {
            "remainingToday": remainingToday,
            "totalUsed": totalUsed,
        },
        "debug": {
            "queueTimeMs": queueTimeMs,
            "workerId": workerId,
            "cacheHit": cacheHit,
        },
        "credits": "@drazeforce",
    }

def buildError(
    requestId, query, searchedTime, processingTimeMs,
    statusCode, errorType, errorMessage,
    remainingToday=0, totalUsed=0,
) -> Dict[str, Any]:
    return {
        "status": "error",
        "statusCode": statusCode,
        "meta": {
            "requestId": requestId,
            "query": query,
            "searchedTime": searchedTime,
            "processingTimeMs": processingTimeMs,
        },
        "data": None,
        "error": {
            "type": errorType,
            "message": errorMessage,
        },
        "usage": {
            "remainingToday": remainingToday,
            "totalUsed": totalUsed,
        },
        "debug": None,
        "credits": "@drazeforce",
    }

errorMap = {
    "not_found": (404, "No data found for the given query."),
    "invalid_api_key": (401, "The provided API key is invalid or inactive."),
    "rate_limit_exceeded": (429, "Too many requests. Slow down."),
    "daily_limit_exceeded": (403, "Daily request limit reached."),
    "timeout": (504, "Request timed out waiting for bot response."),
    "system_disabled": (503, "The API is currently disabled."),
}