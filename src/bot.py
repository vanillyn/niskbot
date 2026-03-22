from __future__ import annotations

import asyncio
import os

import discord
from aiohttp import web
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
    "src.server.economy.currency",
    "src.server.alias",
    "src.server.suggestions",
    "src.server.starboard",
    "src.member.cookies",
]

_WEBHOOK_PORT = int(os.environ.get("WEBHOOK_PORT", "3000"))


class Bot(commands.Bot):
    def __init__(self) -> None:
        setup_discord_logging()
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        intents.reactions = True
        super().__init__(
            command_prefix=":",
            intents=intents,
            help_command=None,
        )
        self.db: Database = Database()
        self._api_runner: web.AppRunner | None = None

    async def setup_hook(self) -> None:
        from src.server.resources import ResourceButton
        from src.server.suggestions import SuggestionButton
        from src.web.server.server import start as start_api

        await self.db.connect()
        await self.db.create_tables()
        self.add_dynamic_items(ResourceButton, SuggestionButton)

        for ext in extensions:
            try:
                await self.load_extension(ext)
                log.info("loaded extension %s", ext)
            except Exception as e:
                log.error("failed to load extension %s: %s", ext, e)

        await self.tree.sync()
        self.tree.on_error = self._on_tree_error

        self._api_runner = await start_api(self)
        log.info("rest api started")

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
        if self._api_runner is not None:
            await self._api_runner.cleanup()
        await self.db.close()
        await super().close()

    async def on_ready(self) -> None:
        assert self.user is not None
        log.info("ready: %s (%s)", self.user, self.user.id)


async def _start_webhook_server() -> None:
    from hypercorn.asyncio import serve
    from hypercorn.config import Config

    from src.web.server.webhook import app

    config = Config()
    config.bind = [f"0.0.0.0:{_WEBHOOK_PORT}"]
    config.accesslog = None
    config.errorlog = log  # type: ignore[assignment]
    log.info("webhook server starting on port %s", _WEBHOOK_PORT)
    await serve(app, config)  # type: ignore[arg-type]


async def _setup_ngrok() -> None:
    from src.server.logging.alerts import set_callback_url
    from src.web.server import ngrok

    use_ngrok = os.environ.get("USE_NGROK", "true").lower() == "true"
    if use_ngrok:
        try:
            public_url = await ngrok.start(_WEBHOOK_PORT)
            set_callback_url(public_url)
            log.info("ngrok tunnel active: %s", public_url)
        except Exception as e:
            log.error("ngrok failed: %s", e)
            manual = os.environ.get("TWITCH_CALLBACK_BASE", "")
            if manual:
                set_callback_url(manual)
                log.info("using manual callback base: %s", manual)
    else:
        base = os.environ.get("TWITCH_CALLBACK_BASE", "")
        set_callback_url(base)
        log.info("using static callback base: %s", base)


async def main() -> None:
    token = os.environ.get("DISCORD_TOKEN", "")
    if not token:
        raise RuntimeError("DISCORD_TOKEN not set")

    await _setup_ngrok()

    bot = Bot()

    async with bot:
        await asyncio.gather(
            bot.start(token),
            _start_webhook_server(),
        )


if __name__ == "__main__":
    asyncio.run(main())
