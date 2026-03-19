from __future__ import annotations

import discord
from discord.ext import commands

extensions: list[str] = ["src.misc.help"]


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

    async def setup_hook(self) -> None:
        for ext in extensions:
            await self.load_extension(ext)
        await self.tree.sync()

    async def on_ready(self) -> None:
        assert self.user is not None
        print(f"ready: {self.user} ({self.user.id})")
