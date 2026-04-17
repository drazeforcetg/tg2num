import asyncio
import os
from dotenv import load_dotenv
load_dotenv()

async def main():
    from tgapi.database import connectDb
    from tgapi.keyManager import generateApiKey
    await connectDb()
    result = await generateApiKey(
        label="admin",
        dailyLimit=1000,
        totalLimit=100000,
        rateLimitPerMinute=20,
    )
    print(f"\nAPI Key: {result['rawKey']}")
    print(f"Key Hash: {result['keyHash']}\n")
    print("Store the raw key securely. It will not be shown again.")

asyncio.run(main())