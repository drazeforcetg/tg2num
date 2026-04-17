import asyncio
import time
from typing import Dict, Optional, Any
from pyrogram import Client, filters
from pyrogram.types import Message
from loguru import logger
from .config import getSettings
from .parser import parseSuccessMessage, isConfirmationMessage, isErrorMessage

_pendingRequests: Dict[str, asyncio.Future] = {}
_correlationMap: Dict[int, str] = {}
_client: Optional[Client] = None

def getTelegramClient() -> Client:
    return _client

async def startClient():
    global _client
    settings = getSettings()
    _client = Client(
        ":memory:",
        api_id=settings.telegramApiId,
        api_hash=settings.telegramApiHash,
        session_string=settings.telegramSessionString,
    )

    @_client.on_message(filters.incoming)
    async def onBotMessage(client: Client, message: Message):
        text = message.text or message.caption or ""
        logger.debug(f"Incoming message from {message.from_user.username if message.from_user else message.chat.username}: {repr(text[:200])}")
        if message.from_user and message.from_user.username:
            senderUsername = message.from_user.username.lower().lstrip("@")
        elif message.chat and message.chat.username:
            senderUsername = message.chat.username.lower().lstrip("@")
        else:
            return
        targetUsername = settings.targetBotUsername.lower().lstrip("@")
        if senderUsername != targetUsername:
            return
        await handleBotMessage(message)

    await _client.start()
    logger.info("Telegram client started")

async def stopClient():
    if _client:
        await _client.stop()

async def handleBotMessage(message: Message):
    text = message.text or message.caption or ""

    if isConfirmationMessage(text):
        return

    correlationId = None

    if message.reply_to_message_id:
        correlationId = _correlationMap.get(message.reply_to_message_id)

    if not correlationId:
        for corrId, future in list(_pendingRequests.items()):
            if not future.done():
                correlationId = corrId
                break

    if not correlationId:
        return

    future = _pendingRequests.get(correlationId)
    if not future or future.done():
        return

    if isErrorMessage(text):
        future.set_result({"found": False, "text": text})
        return

    parsed = parseSuccessMessage(text)
    if parsed:
        future.set_result({"found": True, "data": parsed, "text": text})
    else:
        logger.warning(f"Parser returned None for text: {repr(text[:300])}")
        future.set_result({"found": False, "text": text})

async def queryBot(query: str, correlationId: str, timeoutSec: int = 30) -> Dict[str, Any]:
    settings = getSettings()
    future: asyncio.Future = asyncio.get_event_loop().create_future()
    _pendingRequests[correlationId] = future

    try:
        sentMsg = await _client.send_message(
            settings.targetBotUsername,
            f"/tg {query}",
        )
        _correlationMap[sentMsg.id] = correlationId
        logger.debug(f"Sent message id={sentMsg.id} for correlationId={correlationId}")

        result = await asyncio.wait_for(future, timeout=timeoutSec)
        return result
    except asyncio.TimeoutError:
        return {"found": False, "timeout": True}
    finally:
        _pendingRequests.pop(correlationId, None)
        if "sentMsg" in locals():
            _correlationMap.pop(sentMsg.id, None)