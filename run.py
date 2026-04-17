import asyncio
import os
import sys
import threading
from dotenv import load_dotenv
load_dotenv()

import uvicorn
from tgapi.database import connectDb, disconnectDb
from tgapi.limiter import connectRedis, disconnectRedis
from tgapi.telegramClient import startClient, stopClient
from tgapi.queue import workerPool

async def startAdminBot():
    from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
    from telegram.ext import ApplicationBuilder, CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler, filters
    from tgapi.limiter import setSystemEnabled, getSystemEnabled
    from tgapi.keyManager import generateApiKey, revokeApiKey, rotateApiKey, listAllKeys, updateKeyLimits, resetKeyUsage
    from tgapi.requestLogger import getRecentLogs, getAnalytics
    from tgapi.queue import getQueueStats
    from tgapi.database import getDb
    import hashlib
    from datetime import datetime, timezone

    ADMIN_IDS = [int(x.strip()) for x in os.getenv("ADMIN_TELEGRAM_IDS", "").split(",") if x.strip()]
    API_BASE = os.getenv("API_BASE_URL", "http://localhost:8000")
    _awaitingInput = {}

    def isAdmin(uid): return uid in ADMIN_IDS

    def mainMenu():
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("API Key Management", callback_data="menu_keys")],
            [InlineKeyboardButton("Usage Control", callback_data="menu_usage")],
            [InlineKeyboardButton("Analytics", callback_data="menu_analytics")],
            [InlineKeyboardButton("System Control", callback_data="menu_system")],
        ])

    def keyMenu():
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("Generate Key (auto)", callback_data="key_generate")],
            [InlineKeyboardButton("Generate Key (custom)", callback_data="key_custom_prompt")],
            [InlineKeyboardButton("List All Keys", callback_data="key_list")],
            [InlineKeyboardButton("Revoke Key", callback_data="key_revoke_prompt")],
            [InlineKeyboardButton("Rotate Key", callback_data="key_rotate_prompt")],
            [InlineKeyboardButton("Back", callback_data="menu_main")],
        ])

    def usageMenu():
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("Set Daily Limit", callback_data="usage_daily_prompt")],
            [InlineKeyboardButton("Set Total Limit", callback_data="usage_total_prompt")],
            [InlineKeyboardButton("Set Rate Limit", callback_data="usage_rate_prompt")],
            [InlineKeyboardButton("Reset Key Usage", callback_data="usage_reset_prompt")],
            [InlineKeyboardButton("Back", callback_data="menu_main")],
        ])

    def analyticsMenu():
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("Global Stats", callback_data="analytics_global")],
            [InlineKeyboardButton("Per-Key Usage", callback_data="analytics_perkey")],
            [InlineKeyboardButton("Recent Logs", callback_data="analytics_logs")],
            [InlineKeyboardButton("Back", callback_data="menu_main")],
        ])

    def systemMenu():
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("Enable API", callback_data="system_enable"),
             InlineKeyboardButton("Disable API", callback_data="system_disable")],
            [InlineKeyboardButton("Queue Status", callback_data="system_queue")],
            [InlineKeyboardButton("Back", callback_data="menu_main")],
        ])

    def backOnly(t):
        return InlineKeyboardMarkup([[InlineKeyboardButton("Back", callback_data=t)]])

    async def findKey(prefix):
        keys = await listAllKeys()
        return next((k for k in keys if k["key"].startswith(prefix)), None)

    async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if not isAdmin(update.effective_user.id): return
        await update.message.reply_text("Admin Panel", reply_markup=mainMenu())

    async def handleCallback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        q = update.callback_query
        await q.answer()
        uid = q.from_user.id
        if not isAdmin(uid): return
        d = q.data

        if d == "menu_main":
            await q.edit_message_text("Admin Panel", reply_markup=mainMenu())
        elif d == "menu_keys":
            await q.edit_message_text("API Key Management", reply_markup=keyMenu())
        elif d == "menu_usage":
            await q.edit_message_text("Usage Control", reply_markup=usageMenu())
        elif d == "menu_analytics":
            await q.edit_message_text("Analytics", reply_markup=analyticsMenu())
        elif d == "menu_system":
            enabled = await getSystemEnabled()
            await q.edit_message_text(f"System Control\nAPI: {'ENABLED' if enabled else 'DISABLED'}", reply_markup=systemMenu())
        elif d == "key_generate":
            r = await generateApiKey(label="admin-generated", dailyLimit=100, totalLimit=10000, rateLimitPerMinute=10)
            k = r["rawKey"]
            await q.edit_message_text(f"Key Generated\n\nKey: `{k}`\n\nURL:\n`{API_BASE}/api/v1/lookup?q=USERNAME&api_key={k}`", parse_mode="Markdown", reply_markup=backOnly("menu_keys"))
        elif d == "key_custom_prompt":
            _awaitingInput[uid] = {"action": "key_custom"}
            await q.edit_message_text("Send:\n`<key> <label> <dailyLimit> <totalLimit> <ratePerMin>`\n\nExample:\n`drazeX-mykey john 200 5000 15`", parse_mode="Markdown", reply_markup=backOnly("menu_keys"))
        elif d == "key_list":
            keys = await listAllKeys()
            if not keys:
                msg = "No keys found."
            else:
                lines = [f"{k.get('label','?')} | {k['key'][:12]}... | {'active' if k.get('isActive') else 'revoked'} | {k.get('totalUsed',0)}/{k.get('totalLimit',0)}" for k in keys[:10]]
                msg = "Keys (up to 10):\n\n" + "\n".join(lines)
            await q.edit_message_text(msg, reply_markup=backOnly("menu_keys"))
        elif d == "key_revoke_prompt":
            _awaitingInput[uid] = {"action": "revoke"}
            await q.edit_message_text("Send key hash prefix to revoke:", reply_markup=backOnly("menu_keys"))
        elif d == "key_rotate_prompt":
            _awaitingInput[uid] = {"action": "rotate"}
            await q.edit_message_text("Send key hash prefix to rotate:", reply_markup=backOnly("menu_keys"))
        elif d == "usage_daily_prompt":
            _awaitingInput[uid] = {"action": "set_daily"}
            await q.edit_message_text("Send: `<keyHashPrefix> <dailyLimit>`", parse_mode="Markdown", reply_markup=backOnly("menu_usage"))
        elif d == "usage_total_prompt":
            _awaitingInput[uid] = {"action": "set_total"}
            await q.edit_message_text("Send: `<keyHashPrefix> <totalLimit>`", parse_mode="Markdown", reply_markup=backOnly("menu_usage"))
        elif d == "usage_rate_prompt":
            _awaitingInput[uid] = {"action": "set_rate"}
            await q.edit_message_text("Send: `<keyHashPrefix> <reqPerMinute>`", parse_mode="Markdown", reply_markup=backOnly("menu_usage"))
        elif d == "usage_reset_prompt":
            _awaitingInput[uid] = {"action": "reset_usage"}
            await q.edit_message_text("Send key hash prefix to reset:", reply_markup=backOnly("menu_usage"))
        elif d == "analytics_global":
            stats = await getAnalytics()
            qs = getQueueStats()
            await q.edit_message_text(
                f"Global Stats\n\nTotal: {stats['totalRequests']}\nSuccess: {stats['totalSuccess']}\nErrors: {stats['totalErrors']}\n\nQueue: {qs['queueSize']}\nWorkers: {qs['activeWorkers']}\nProcessed: {qs['totalProcessed']}",
                reply_markup=backOnly("menu_analytics")
            )
        elif d == "analytics_perkey":
            keys = await listAllKeys()
            lines = [f"{k.get('label','?')} | used: {k.get('totalUsed',0)} | daily: {k.get('dailyLimit',0)} | total: {k.get('totalLimit',0)}" for k in keys[:10]]
            await q.edit_message_text("Per-Key:\n\n" + ("\n".join(lines) or "Empty"), reply_markup=backOnly("menu_analytics"))
        elif d == "analytics_logs":
            logs = await getRecentLogs(10)
            if not logs:
                msg = "No logs."
            else:
                lines = [f"{str(l.get('createdAt',''))[:19]} | {l.get('status')} | {l.get('query')} | {l.get('processingTimeMs')}ms" for l in logs]
                msg = "Recent Logs:\n\n" + "\n".join(lines)
            await q.edit_message_text(msg, reply_markup=backOnly("menu_analytics"))
        elif d == "system_enable":
            await setSystemEnabled(True)
            await q.edit_message_text("API ENABLED.", reply_markup=backOnly("menu_system"))
        elif d == "system_disable":
            await setSystemEnabled(False)
            await q.edit_message_text("API DISABLED.", reply_markup=backOnly("menu_system"))
        elif d == "system_queue":
            qs = getQueueStats()
            await q.edit_message_text(f"Queue: {qs['queueSize']}\nWorkers: {qs['activeWorkers']}\nProcessed: {qs['totalProcessed']}", reply_markup=backOnly("menu_system"))

    async def handleText(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        uid = update.effective_user.id
        if not isAdmin(uid) or uid not in _awaitingInput: return
        action = _awaitingInput.pop(uid)["action"]
        text = update.message.text.strip()

        if action == "key_custom":
            parts = text.split()
            if len(parts) != 5 or not all(parts[i].isdigit() for i in [2,3,4]):
                await update.message.reply_text("Invalid format.", reply_markup=mainMenu()); return
            rawKey, label, daily, total, rate = parts
            if len(rawKey) < 6:
                await update.message.reply_text("Key too short (min 6 chars).", reply_markup=mainMenu()); return
            kh = hashlib.sha256(rawKey.encode()).hexdigest()
            if await getDb()["apiKeys"].find_one({"key": kh}):
                await update.message.reply_text("Key already exists.", reply_markup=mainMenu()); return
            await getDb()["apiKeys"].insert_one({
                "key": kh, "label": label, "dailyLimit": int(daily), "totalLimit": int(total),
                "rateLimitPerMinute": int(rate), "totalUsed": 0, "isActive": True,
                "createdAt": datetime.now(timezone.utc), "lastUsedAt": None,
            })
            await update.message.reply_text(
                f"Custom key created.\n\nKey: `{rawKey}`\nLabel: {label}\nDaily: {daily} | Total: {total} | Rate: {rate}/min\n\nURL:\n`{API_BASE}/api/v1/lookup?q=USERNAME&api_key={rawKey}`",
                parse_mode="Markdown", reply_markup=mainMenu()
            )
        elif action == "revoke":
            m = await findKey(text)
            if not m: await update.message.reply_text("Not found.", reply_markup=mainMenu()); return
            await revokeApiKey(m["key"])
            await update.message.reply_text("Key revoked.", reply_markup=mainMenu())
        elif action == "rotate":
            m = await findKey(text)
            if not m: await update.message.reply_text("Not found.", reply_markup=mainMenu()); return
            r = await rotateApiKey(m["key"])
            nk = r["rawKey"]
            await update.message.reply_text(f"Rotated.\n\nNew Key: `{nk}`\n\nURL:\n`{API_BASE}/api/v1/lookup?q=USERNAME&api_key={nk}`", parse_mode="Markdown", reply_markup=mainMenu())
        elif action in ("set_daily", "set_total", "set_rate"):
            parts = text.split()
            if len(parts) != 2 or not parts[1].isdigit():
                await update.message.reply_text("Invalid format.", reply_markup=mainMenu()); return
            m = await findKey(parts[0])
            if not m: await update.message.reply_text("Not found.", reply_markup=mainMenu()); return
            lim = int(parts[1])
            if action == "set_daily":
                await updateKeyLimits(m["key"], dailyLimit=lim)
                await update.message.reply_text(f"Daily limit set to {lim}.", reply_markup=mainMenu())
            elif action == "set_total":
                await updateKeyLimits(m["key"], totalLimit=lim)
                await update.message.reply_text(f"Total limit set to {lim}.", reply_markup=mainMenu())
            else:
                await getDb()["apiKeys"].update_one({"key": m["key"]}, {"$set": {"rateLimitPerMinute": lim}})
                await update.message.reply_text(f"Rate limit set to {lim}/min.", reply_markup=mainMenu())
        elif action == "reset_usage":
            m = await findKey(text)
            if not m: await update.message.reply_text("Not found.", reply_markup=mainMenu()); return
            await resetKeyUsage(m["key"])
            await update.message.reply_text("Usage reset.", reply_markup=mainMenu())

    botToken = os.getenv("ADMIN_BOT_TOKEN")
    if not botToken:
        print("ADMIN_BOT_TOKEN not set, skipping admin bot")
        return
    app = ApplicationBuilder().token(botToken).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(handleCallback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handleText))
    await app.initialize()
    await app.start()
    await app.updater.start_polling()
    print("Admin bot started")

async def main():
    from tgapi.app import app as fastapiApp

    await connectDb()
    await connectRedis()
    await startClient()
    await workerPool.start()
    await startAdminBot()

    config = uvicorn.Config(fastapiApp, host="0.0.0.0", port=8000, loop="none", log_level="info")
    server = uvicorn.Server(config)
    await server.serve()

    await workerPool.stop()
    await stopClient()
    await disconnectRedis()
    await disconnectDb()

if __name__ == "__main__":
    asyncio.run(main())