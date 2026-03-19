from __future__ import annotations

import asyncio
import os

from dotenv import load_dotenv

from src.bot import Bot


async def main() -> None:
    load_dotenv()
    token: str = os.environ["DISCORD_TOKEN"]
    async with Bot() as bot:
        await bot.start(token)


asyncio.run(main())
