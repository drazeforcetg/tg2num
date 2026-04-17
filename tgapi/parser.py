import re
from typing import Optional, Dict, Any

_telegramIdPattern = re.compile(r"Telegram\s*ID[^\d]*(\d+)", re.IGNORECASE)
_numberPattern = re.compile(r"Number[^\d]*(\d+)", re.IGNORECASE)
_countryPattern = re.compile(r"Country\s*(?!Code)[^:\n]*:\s*([^\n\r]+)", re.IGNORECASE)
_countryCodePattern = re.compile(r"Country\s*Code[^:\n]*:\s*([^\n\r]+)", re.IGNORECASE)
_notFoundPatterns = [
    re.compile(r"not found", re.IGNORECASE),
    re.compile(r"no result", re.IGNORECASE),
    re.compile(r"couldn'?t find", re.IGNORECASE),
    re.compile(r"user not found", re.IGNORECASE),
    re.compile(r"invalid username", re.IGNORECASE),
]

def parseSuccessMessage(text: str) -> Optional[Dict[str, Any]]:
    for pat in _notFoundPatterns:
        if pat.search(text):
            return None

    telegramIdMatch = _telegramIdPattern.search(text)
    numberMatch = _numberPattern.search(text)

    if not telegramIdMatch or not numberMatch:
        return None

    countryCodeMatch = _countryCodePattern.search(text)
    countryMatch = _countryPattern.search(text)

    telegramId = int(telegramIdMatch.group(1))
    phone = numberMatch.group(1).strip()
    countryCode = countryCodeMatch.group(1).strip() if countryCodeMatch else ""
    country = countryMatch.group(1).strip() if countryMatch else ""

    return {
        "telegramId": telegramId,
        "phone": phone,
        "country": country,
        "countryCode": countryCode,
    }

def isConfirmationMessage(text: str) -> bool:
    return bool(re.search(r"successfully fetched|fetching|looking up", text, re.IGNORECASE))

def isErrorMessage(text: str) -> bool:
    for pat in _notFoundPatterns:
        if pat.search(text):
            return True
    return False