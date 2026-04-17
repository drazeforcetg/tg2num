import asyncio
import os
from dotenv import load_dotenv
load_dotenv()

async def main():
    from pyrogram import Client
    apiId = int(os.getenv("TELEGRAM_API_ID"))
    apiHash = os.getenv("TELEGRAM_API_HASH")
    async with Client("gen_session", api_id=apiId, api_hash=apiHash) as c:
        sessionString = await c.export_session_string()
        print(f"\nTELEGRAM_SESSION_STRING={sessionString}\n")

asyncio.run(main())