from __future__ import annotations

import os
import time
from typing import TYPE_CHECKING

import discord
from discord import ui
from discord.ext import commands, tasks

from src.apis.twitch import TwitchClient
from src.data.config import GuildConfig
from src.utils.logger import get_logger
from src.utils.placeholders import resolve_text
from src.utils.ui import BaseLayout

if TYPE_CHECKING:
    from src.bot import Bot

log = get_logger("alerts")

_TWITCH_INTERVAL = 120


class AlertsCog(commands.Cog, name="alerts"):
    def __init__(self, bot: "Bot") -> None:
        self.bot = bot
        self._twitch: TwitchClient | None = None
        client_id = os.environ.get("TWITCH_CLIENT_ID", "")
        client_secret = os.environ.get("TWITCH_CLIENT_SECRET", "")
        if client_id and client_secret:
            self._twitch = TwitchClient(client_id, client_secret)
            self._twitch_poll.start()
        else:
            log.warning("twitch env vars missing — twitch alerts disabled")

    async def cog_unload(self) -> None:
        self._twitch_poll.cancel()
        if self._twitch is not None:
            await self._twitch.close()

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        guild = member.guild
        cfg = await GuildConfig.load(self.bot.db, guild.id)
        if not cfg.log.alerts or not cfg.log.alerts_joins:
            return
        channel_id = cfg.log.alerts_joins_channel or cfg.log.alerts_channel
        if channel_id is None:
            return
        channel = guild.get_channel(channel_id)
        if not isinstance(channel, discord.TextChannel):
            return
        template = cfg.log.alerts_joins_message
        if not template:
            return
        text = resolve_text(template, guild, member, channel)
        layout = BaseLayout()
        layout.add_container(ui.TextDisplay(text), accent_color=0x57F287)
        try:
            await channel.send(view=layout)
        except discord.HTTPException as e:
            log.error("join alert failed in guild %s: %s", guild.id, e)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member) -> None:
        guild = member.guild
        cfg = await GuildConfig.load(self.bot.db, guild.id)
        if not cfg.log.alerts or not cfg.log.alerts_leaves:
            return
        channel_id = cfg.log.alerts_leaves_channel or cfg.log.alerts_channel
        if channel_id is None:
            return
        channel = guild.get_channel(channel_id)
        if not isinstance(channel, discord.TextChannel):
            return
        template = cfg.log.alerts_leaves_message
        if not template:
            return
        text = resolve_text(template, guild, member, channel)
        layout = BaseLayout()
        layout.add_container(ui.TextDisplay(text), accent_color=0xED4245)
        try:
            await channel.send(view=layout)
        except discord.HTTPException as e:
            log.error("leave alert failed in guild %s: %s", guild.id, e)

    @tasks.loop(seconds=_TWITCH_INTERVAL)
    async def _twitch_poll(self) -> None:
        if self._twitch is None:
            return
        for guild in self.bot.guilds:
            try:
                await self._poll_guild(guild)
            except Exception as e:
                log.error("twitch poll error guild %s: %s", guild.id, e)

    async def _poll_guild(self, guild: discord.Guild) -> None:
        assert self._twitch is not None
        cfg = await GuildConfig.load(self.bot.db, guild.id)
        if not cfg.log.alerts or not cfg.log.alerts_twitch:
            return
        streamer = cfg.log.alerts_twitch_streamer
        if not streamer:
            return
        channel_id = cfg.log.alerts_twitch_channel or cfg.log.alerts_channel
        if channel_id is None:
            return
        channel = guild.get_channel(channel_id)
        if not isinstance(channel, discord.TextChannel):
            return

        was_live = await self._get_cache(guild.id, streamer)
        try:
            stream = await self._twitch.get_stream(streamer)
        except Exception as e:
            log.warning("twitch api error for %s: %s", streamer, e)
            return

        is_live = stream is not None
        await self._set_cache(guild.id, streamer, is_live)

        if is_live and not was_live:
            template = cfg.log.alerts_twitch_message or f"{streamer} is live!"
            text = (
                template.replace("{streamer}", streamer)
                .replace("{title}", str(stream.get("title", "")))
                .replace("{game}", str(stream.get("game_name", "")))
                .replace("{url}", f"https://twitch.tv/{streamer}")
            )
            layout = BaseLayout()
            layout.add_container(ui.TextDisplay(text), accent_color=0x9146FF)
            try:
                await channel.send(view=layout)
                log.info("twitch alert sent for %s in guild %s", streamer, guild.id)
            except discord.HTTPException as e:
                log.error("twitch alert send failed guild %s: %s", guild.id, e)

    async def _get_cache(self, guild_id: int, streamer: str) -> bool:
        row = await self.bot.db.fetchone(
            "select is_live from twitch_stream_cache where guild_id = ? and streamer = ?",
            (guild_id, streamer),
        )
        return bool(int(row[0])) if row is not None else False  # type: ignore[arg-type]

    async def _set_cache(self, guild_id: int, streamer: str, is_live: bool) -> None:
        await self.bot.db.execute(
            "insert into twitch_stream_cache (guild_id, streamer, is_live, last_checked)"
            " values (?, ?, ?, ?)"
            " on conflict (guild_id, streamer) do update set"
            " is_live = excluded.is_live, last_checked = excluded.last_checked",
            (guild_id, streamer, int(is_live), int(time.time())),
        )

    @_twitch_poll.before_loop
    async def _before_poll(self) -> None:
        await self.bot.wait_until_ready()


async def setup(bot: "Bot") -> None:
    await bot.add_cog(AlertsCog(bot))
