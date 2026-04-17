import os
from dotenv import load_dotenv
load_dotenv()

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from tgapi.limiter import setSystemEnabled, getSystemEnabled
from tgapi.keyManager import generateApiKey, revokeApiKey, rotateApiKey, listAllKeys, updateKeyLimits, resetKeyUsage
from tgapi.requestLogger import getRecentLogs, getAnalytics
from tgapi.queue import getQueueStats
from tgapi.database import getDb
from datetime import datetime, timezone
import hashlib

ADMIN_IDS = [int(x.strip()) for x in os.getenv("ADMIN_TELEGRAM_IDS", "").split(",") if x.strip()]
API_BASE = os.getenv("API_BASE_URL", "http://localhost:8000")

_awaitingInput: dict = {}

def isAdmin(userId: int) -> bool:
    return userId in ADMIN_IDS

def mainMenu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("API Key Management", callback_data="menu_keys")],
        [InlineKeyboardButton("Usage Control", callback_data="menu_usage")],
        [InlineKeyboardButton("Analytics", callback_data="menu_analytics")],
        [InlineKeyboardButton("System Control", callback_data="menu_system")],
    ])

def keyMenu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Generate Key (auto)", callback_data="key_generate")],
        [InlineKeyboardButton("Generate Key (custom)", callback_data="key_custom_prompt")],
        [InlineKeyboardButton("List All Keys", callback_data="key_list")],
        [InlineKeyboardButton("Revoke Key", callback_data="key_revoke_prompt")],
        [InlineKeyboardButton("Rotate Key", callback_data="key_rotate_prompt")],
        [InlineKeyboardButton("Back", callback_data="menu_main")],
    ])

def usageMenu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Set Daily Limit", callback_data="usage_daily_prompt")],
        [InlineKeyboardButton("Set Total Limit", callback_data="usage_total_prompt")],
        [InlineKeyboardButton("Set Rate Limit", callback_data="usage_rate_prompt")],
        [InlineKeyboardButton("Reset Key Usage", callback_data="usage_reset_prompt")],
        [InlineKeyboardButton("Back", callback_data="menu_main")],
    ])

def analyticsMenu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Global Stats", callback_data="analytics_global")],
        [InlineKeyboardButton("Per-Key Usage", callback_data="analytics_perkey")],
        [InlineKeyboardButton("Recent Logs", callback_data="analytics_logs")],
        [InlineKeyboardButton("Back", callback_data="menu_main")],
    ])

def systemMenu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Enable API", callback_data="system_enable"),
         InlineKeyboardButton("Disable API", callback_data="system_disable")],
        [InlineKeyboardButton("Queue Status", callback_data="system_queue")],
        [InlineKeyboardButton("Back", callback_data="menu_main")],
    ])

def backOnly(t: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("Back", callback_data=t)]])

async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not isAdmin(update.effective_user.id):
        return
    await update.message.reply_text("Admin Panel", reply_markup=mainMenu())

async def handleCallback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    userId = query.from_user.id
    if not isAdmin(userId):
        return
    data = query.data

    if data == "menu_main":
        await query.edit_message_text("Admin Panel", reply_markup=mainMenu())
    elif data == "menu_keys":
        await query.edit_message_text("API Key Management", reply_markup=keyMenu())
    elif data == "menu_usage":
        await query.edit_message_text("Usage Control", reply_markup=usageMenu())
    elif data == "menu_analytics":
        await query.edit_message_text("Analytics", reply_markup=analyticsMenu())
    elif data == "menu_system":
        enabled = await getSystemEnabled()
        await query.edit_message_text(f"System Control\nAPI: {'ENABLED' if enabled else 'DISABLED'}", reply_markup=systemMenu())

    elif data == "key_generate":
        result = await generateApiKey(label="admin-generated", dailyLimit=100, totalLimit=10000, rateLimitPerMinute=10)
        rawKey = result["rawKey"]
        await query.edit_message_text(
            f"New Key Generated\n\nKey: `{rawKey}`\n\nURL:\n`{API_BASE}/api/v1/lookup?q=USERNAME&api_key={rawKey}`",
            parse_mode="Markdown", reply_markup=backOnly("menu_keys")
        )

    elif data == "key_custom_prompt":
        _awaitingInput[userId] = {"action": "key_custom"}
        await query.edit_message_text(
            "Send custom key details:\n\n`<key> <label> <dailyLimit> <totalLimit> <ratePerMin>`\n\nExample:\n`drazeX-mykey-001 john 200 5000 15`",
            parse_mode="Markdown", reply_markup=backOnly("menu_keys")
        )

    elif data == "key_list":
        keys = await listAllKeys()
        if not keys:
            msg = "No keys found."
        else:
            lines = [f"{k.get('label','?')} | {k['key'][:12]}... | {'active' if k.get('isActive') else 'revoked'} | {k.get('totalUsed',0)}/{k.get('totalLimit',0)}" for k in keys[:10]]
            msg = "Keys (up to 10):\n\n" + "\n".join(lines)
        await query.edit_message_text(msg, reply_markup=backOnly("menu_keys"))

    elif data == "key_revoke_prompt":
        _awaitingInput[userId] = {"action": "revoke"}
        await query.edit_message_text("Send key hash prefix (first 12 chars from list):", reply_markup=backOnly("menu_keys"))

    elif data == "key_rotate_prompt":
        _awaitingInput[userId] = {"action": "rotate"}
        await query.edit_message_text("Send key hash prefix to rotate:", reply_markup=backOnly("menu_keys"))

    elif data == "usage_daily_prompt":
        _awaitingInput[userId] = {"action": "set_daily"}
        await query.edit_message_text("Send: `<keyHashPrefix> <dailyLimit>`", parse_mode="Markdown", reply_markup=backOnly("menu_usage"))

    elif data == "usage_total_prompt":
        _awaitingInput[userId] = {"action": "set_total"}
        await query.edit_message_text("Send: `<keyHashPrefix> <totalLimit>`", parse_mode="Markdown", reply_markup=backOnly("menu_usage"))

    elif data == "usage_rate_prompt":
        _awaitingInput[userId] = {"action": "set_rate"}
        await query.edit_message_text("Send: `<keyHashPrefix> <requestsPerMinute>`", parse_mode="Markdown", reply_markup=backOnly("menu_usage"))

    elif data == "usage_reset_prompt":
        _awaitingInput[userId] = {"action": "reset_usage"}
        await query.edit_message_text("Send key hash prefix to reset usage:", reply_markup=backOnly("menu_usage"))

    elif data == "analytics_global":
        stats = await getAnalytics()
        q2 = getQueueStats()
        await query.edit_message_text(
            f"Global Stats\n\nTotal: {stats['totalRequests']}\nSuccess: {stats['totalSuccess']}\nErrors: {stats['totalErrors']}\n\nQueue: {q2['queueSize']}\nWorkers: {q2['activeWorkers']}\nProcessed: {q2['totalProcessed']}",
            reply_markup=backOnly("menu_analytics")
        )

    elif data == "analytics_perkey":
        keys = await listAllKeys()
        if not keys:
            msg = "No keys."
        else:
            lines = [f"{k.get('label','?')}\n  Used: {k.get('totalUsed',0)} | Daily: {k.get('dailyLimit',0)} | Total: {k.get('totalLimit',0)}" for k in keys[:10]]
            msg = "Per-Key Usage:\n\n" + "\n\n".join(lines)
        await query.edit_message_text(msg, reply_markup=backOnly("menu_analytics"))

    elif data == "analytics_logs":
        logs = await getRecentLogs(10)
        if not logs:
            msg = "No logs yet."
        else:
            lines = [f"{str(l.get('createdAt',''))[:19]} | {l.get('status')} | {l.get('query')} | {l.get('processingTimeMs')}ms" for l in logs]
            msg = "Recent 10:\n\n" + "\n".join(lines)
        await query.edit_message_text(msg, reply_markup=backOnly("menu_analytics"))

    elif data == "system_enable":
        await setSystemEnabled(True)
        await query.edit_message_text("API is now ENABLED.", reply_markup=backOnly("menu_system"))

    elif data == "system_disable":
        await setSystemEnabled(False)
        await query.edit_message_text("API is now DISABLED.", reply_markup=backOnly("menu_system"))

    elif data == "system_queue":
        q2 = getQueueStats()
        await query.edit_message_text(
            f"Queue Status\n\nPending: {q2['queueSize']}\nActive Workers: {q2['activeWorkers']}\nTotal Processed: {q2['totalProcessed']}",
            reply_markup=backOnly("menu_system")
        )

async def handleText(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    userId = update.effective_user.id
    if not isAdmin(userId) or userId not in _awaitingInput:
        return
    action = _awaitingInput.pop(userId)["action"]
    text = update.message.text.strip()

    async def findKey(prefix):
        keys = await listAllKeys()
        return next((k for k in keys if k["key"].startswith(prefix)), None)

    if action == "key_custom":
        parts = text.split()
        if len(parts) != 5:
            await update.message.reply_text("Invalid. Need: `<key> <label> <daily> <total> <rate>`", parse_mode="Markdown", reply_markup=mainMenu())
            return
        rawKey, label, daily, total, rate = parts
        if len(rawKey) < 8:
            await update.message.reply_text("Key too short (min 8 chars).", reply_markup=mainMenu())
            return
        if not (daily.isdigit() and total.isdigit() and rate.isdigit()):
            await update.message.reply_text("Limits must be numbers.", reply_markup=mainMenu())
            return
        keyHash = hashlib.sha256(rawKey.encode()).hexdigest()
        existing = await getDb()["apiKeys"].find_one({"key": keyHash})
        if existing:
            await update.message.reply_text("Key already exists.", reply_markup=mainMenu())
            return
        await getDb()["apiKeys"].insert_one({
            "key": keyHash, "label": label,
            "dailyLimit": int(daily), "totalLimit": int(total),
            "rateLimitPerMinute": int(rate),
            "totalUsed": 0, "isActive": True,
            "createdAt": datetime.now(timezone.utc), "lastUsedAt": None,
        })
        await update.message.reply_text(
            f"Custom key created.\n\nKey: `{rawKey}`\nLabel: {label} | Daily: {daily} | Total: {total} | Rate: {rate}/min\n\nURL:\n`{API_BASE}/api/v1/lookup?q=USERNAME&api_key={rawKey}`",
            parse_mode="Markdown", reply_markup=mainMenu()
        )

    elif action == "revoke":
        matched = await findKey(text)
        if not matched:
            await update.message.reply_text("Key not found.", reply_markup=mainMenu())
            return
        await revokeApiKey(matched["key"])
        await update.message.reply_text("Key revoked.", reply_markup=mainMenu())

    elif action == "rotate":
        matched = await findKey(text)
        if not matched:
            await update.message.reply_text("Key not found.", reply_markup=mainMenu())
            return
        result = await rotateApiKey(matched["key"])
        newKey = result["rawKey"]
        await update.message.reply_text(
            f"Key rotated.\n\nNew Key: `{newKey}`\n\nURL:\n`{API_BASE}/api/v1/lookup?q=USERNAME&api_key={newKey}`",
            parse_mode="Markdown", reply_markup=mainMenu()
        )

    elif action in ("set_daily", "set_total", "set_rate"):
        parts = text.split()
        if len(parts) != 2 or not parts[1].isdigit():
            await update.message.reply_text("Invalid. Send: `<keyHashPrefix> <number>`", parse_mode="Markdown", reply_markup=mainMenu())
            return
        matched = await findKey(parts[0])
        if not matched:
            await update.message.reply_text("Key not found.", reply_markup=mainMenu())
            return
        limit = int(parts[1])
        if action == "set_daily":
            await updateKeyLimits(matched["key"], dailyLimit=limit)
            await update.message.reply_text(f"Daily limit set to {limit}.", reply_markup=mainMenu())
        elif action == "set_total":
            await updateKeyLimits(matched["key"], totalLimit=limit)
            await update.message.reply_text(f"Total limit set to {limit}.", reply_markup=mainMenu())
        else:
            await getDb()["apiKeys"].update_one({"key": matched["key"]}, {"$set": {"rateLimitPerMinute": limit}})
            await update.message.reply_text(f"Rate limit set to {limit}/min.", reply_markup=mainMenu())

    elif action == "reset_usage":
        matched = await findKey(text)
        if not matched:
            await update.message.reply_text("Key not found.", reply_markup=mainMenu())
            return
        await resetKeyUsage(matched["key"])
        await update.message.reply_text("Usage reset.", reply_markup=mainMenu())