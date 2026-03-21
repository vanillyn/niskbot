from __future__ import annotations

import discord
from discord.ext import commands

from src.data.db import Database
from src.utils.logger import get_logger, setup_discord_logging

log = get_logger("bot")

extensions: list[str] = [
    "src.misc.help",
    "src.misc.config",
    "src.misc.echo",
    "src.server.moderation.commands.actions",
    "src.server.resources",
    "src.server.containers",
    "src.server.logging.alerts",
]


class Bot(commands.Bot):
    def __init__(self) -> None:
        setup_discord_logging()
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
        from src.server.resources import ResourceButton

        await self.db.connect()
        await self.db.create_tables()
        self.add_dynamic_items(ResourceButton)
        for ext in extensions:
            try:
                await self.load_extension(ext)
                log.info("loaded extension %s", ext)
            except Exception as e:
                log.error("failed to load extension %s: %s", ext, e)
        await self.tree.sync()
        self.tree.on_error = self._on_tree_error

    async def _on_tree_error(
        self,
        interaction: discord.Interaction,
        error: Exception,
    ) -> None:
        log.error("tree error: %s", error, exc_info=error)
        msg = "something went wrong"
        try:
            if interaction.response.is_done():
                await interaction.followup.send(msg, ephemeral=True)
            else:
                await interaction.response.send_message(msg, ephemeral=True)
        except Exception:
            pass

    async def close(self) -> None:
        await self.db.close()
        await super().close()

    async def on_ready(self) -> None:
        assert self.user is not None
        log.info("ready: %s (%s)", self.user, self.user.id)
