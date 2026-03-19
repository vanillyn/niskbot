from __future__ import annotations

import discord
from discord.ext import commands

from src.data.db import Database

extensions: list[str] = [
    "src.misc.help",
    "src.misc.config",
    "src.server.moderation.commands.actions",
]


class Bot(commands.Bot):
    def __init__(self) -> None:
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        super().__init__(
            command_prefix=":",
            intents=intents,
            help_command=None,
        )
        self.db: Database = Database()

    async def setup_hook(self) -> None:
        await self.db.connect()
        await self.db.create_tables()
        for ext in extensions:
            await self.load_extension(ext)
        await self.tree.sync()

    async def close(self) -> None:
        await self.db.close()
        await super().close()

    async def on_ready(self) -> None:
        assert self.user is not None
        print(f"ready: {self.user} ({self.user.id})")
