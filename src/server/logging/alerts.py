from __future__ import annotations

import os
import time
from typing import TYPE_CHECKING

import discord
from discord import app_commands, ui
from discord.ext import commands, tasks

from src.apis.twitch import TwitchClient
from src.apis.youtube import YouTubeClient
from src.data.config import GuildConfig
from src.data.economy import (
    delete_streamer_alert,
    get_stream_cache,
    get_streamer_alerts,
    set_stream_cache,
    upsert_streamer_alert,
)
from src.member.util import _is_admin
from src.utils.logger import get_logger
from src.utils.placeholders import resolve_text
from src.utils.ui import BaseLayout

if TYPE_CHECKING:
    from src.bot import Bot

log = get_logger("alerts")

_TWITCH_INTERVAL = 120
_YOUTUBE_INTERVAL = 300


def _resolve_twitch(template: str, streamer: str, data: dict[str, object]) -> str:
    return (
        template.replace("{streamer}", streamer)
        .replace("{title}", str(data.get("title", "")))
        .replace("{game}", str(data.get("game_name", "")))
        .replace("{url}", f"https://twitch.tv/{streamer}")
    )


def _resolve_youtube(template: str, streamer: str, data: dict[str, object]) -> str:
    return (
        template.replace("{channel}", str(data.get("channel_title", streamer)))
        .replace("{title}", str(data.get("title", "")))
        .replace("{url}", str(data.get("url", "")))
    )


class AlertsCog(commands.Cog, name="alerts"):
    def __init__(self, bot: "Bot") -> None:
        self.bot = bot
        self._twitch: TwitchClient | None = None
        self._youtube: YouTubeClient | None = None

        client_id = os.environ.get("TWITCH_CLIENT_ID", "")
        client_secret = os.environ.get("TWITCH_CLIENT_SECRET", "")
        if client_id and client_secret:
            self._twitch = TwitchClient(client_id, client_secret)
            self._twitch_poll.start()
        else:
            log.warning("twitch env vars missing — twitch alerts disabled")

        yt_key = os.environ.get("YOUTUBE_API_KEY", "")
        if yt_key:
            self._youtube = YouTubeClient(yt_key)
            self._youtube_poll.start()
        else:
            log.warning("youtube api key missing — youtube alerts disabled")

    async def cog_unload(self) -> None:
        self._twitch_poll.cancel()
        self._youtube_poll.cancel()
        if self._twitch is not None:
            await self._twitch.close()
        if self._youtube is not None:
            await self._youtube.close()

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
            cfg = await GuildConfig.load(self.bot.db, guild.id)
            if not cfg.log.alerts_twitch:
                continue
            entries = await get_streamer_alerts(self.bot.db, guild.id, "twitch")
            for streamer, channel_id, message in entries:
                try:
                    await self._poll_twitch(guild, streamer, channel_id, message)
                except Exception as e:
                    log.error(
                        "twitch poll error %s guild %s: %s", streamer, guild.id, e
                    )

    async def _poll_twitch(
        self,
        guild: discord.Guild,
        streamer: str,
        channel_id: int,
        message: str | None,
    ) -> None:
        assert self._twitch is not None
        channel = guild.get_channel(channel_id)
        if not isinstance(channel, discord.TextChannel):
            return

        was_live = await get_stream_cache(self.bot.db, guild.id, "twitch", streamer)
        try:
            stream = await self._twitch.get_stream(streamer)
        except Exception as e:
            log.warning("twitch api error for %s: %s", streamer, e)
            return

        is_live = stream is not None
        await set_stream_cache(
            self.bot.db, guild.id, "twitch", streamer, is_live, int(time.time())
        )

        if is_live and not was_live:
            data: dict[str, object] = stream or {}
            text = _resolve_twitch(
                message or f"{streamer} is now live!",
                streamer,
                data,
            )
            layout = BaseLayout()
            layout.add_container(ui.TextDisplay(text), accent_color=0x9146FF)
            try:
                await channel.send(view=layout)
                log.info("twitch alert sent for %s in guild %s", streamer, guild.id)
            except discord.HTTPException as e:
                log.error("twitch alert failed %s guild %s: %s", streamer, guild.id, e)

    @tasks.loop(seconds=_YOUTUBE_INTERVAL)
    async def _youtube_poll(self) -> None:
        if self._youtube is None:
            return
        for guild in self.bot.guilds:
            cfg = await GuildConfig.load(self.bot.db, guild.id)
            if not cfg.log.alerts_youtube:
                continue
            entries = await get_streamer_alerts(self.bot.db, guild.id, "youtube")
            for channel_id_str, discord_channel_id, message in entries:
                try:
                    await self._poll_youtube(
                        guild, channel_id_str, discord_channel_id, message
                    )
                except Exception as e:
                    log.error(
                        "youtube poll error %s guild %s: %s",
                        channel_id_str,
                        guild.id,
                        e,
                    )

    async def _poll_youtube(
        self,
        guild: discord.Guild,
        yt_channel_id: str,
        discord_channel_id: int,
        message: str | None,
    ) -> None:
        assert self._youtube is not None
        channel = guild.get_channel(discord_channel_id)
        if not isinstance(channel, discord.TextChannel):
            return

        was_live = await get_stream_cache(
            self.bot.db, guild.id, "youtube", yt_channel_id
        )
        try:
            stream = await self._youtube.get_live_stream(yt_channel_id)
        except Exception as e:
            log.warning("youtube api error for %s: %s", yt_channel_id, e)
            return

        is_live = stream is not None
        await set_stream_cache(
            self.bot.db, guild.id, "youtube", yt_channel_id, is_live, int(time.time())
        )

        if is_live and not was_live:
            data: dict[str, object] = stream or {}
            channel_title = str(data.get("channel_title", yt_channel_id))
            text = _resolve_youtube(
                message or f"{channel_title} is now live!",
                yt_channel_id,
                data,
            )
            layout = BaseLayout()
            layout.add_container(ui.TextDisplay(text), accent_color=0xFF0000)
            try:
                await channel.send(view=layout)
                log.info(
                    "youtube alert sent for %s in guild %s", yt_channel_id, guild.id
                )
            except discord.HTTPException as e:
                log.error(
                    "youtube alert failed %s guild %s: %s", yt_channel_id, guild.id, e
                )

    @_twitch_poll.before_loop
    async def _before_twitch(self) -> None:
        await self.bot.wait_until_ready()

    @_youtube_poll.before_loop
    async def _before_youtube(self) -> None:
        await self.bot.wait_until_ready()

    alerts = app_commands.Group(name="alerts", description="manage streamer alerts")

    @alerts.command(name="twitch-add", description="add a twitch streamer alert")
    @app_commands.describe(
        streamer="twitch username",
        channel="channel to post alerts in",
        message="custom message ({streamer}, {title}, {game}, {url})",
    )
    async def twitch_add(
        self,
        interaction: discord.Interaction,
        streamer: str,
        channel: discord.TextChannel,
        message: str | None = None,
    ) -> None:
        if not isinstance(interaction.user, discord.Member) or not _is_admin(
            interaction.user
        ):
            await interaction.response.send_message(
                "missing permissions", ephemeral=True
            )
            return
        if interaction.guild is None:
            return
        await upsert_streamer_alert(
            self.bot.db,
            interaction.guild.id,
            "twitch",
            streamer.lower(),
            channel.id,
            message,
        )
        await interaction.response.send_message(
            f"twitch alert added for **{streamer}** → {channel.mention}", ephemeral=True
        )

    @alerts.command(name="twitch-remove", description="remove a twitch streamer alert")
    @app_commands.describe(streamer="twitch username")
    async def twitch_remove(
        self,
        interaction: discord.Interaction,
        streamer: str,
    ) -> None:
        if not isinstance(interaction.user, discord.Member) or not _is_admin(
            interaction.user
        ):
            await interaction.response.send_message(
                "missing permissions", ephemeral=True
            )
            return
        if interaction.guild is None:
            return
        removed = await delete_streamer_alert(
            self.bot.db, interaction.guild.id, "twitch", streamer.lower()
        )
        msg = (
            f"removed twitch alert for **{streamer}**" if removed else "alert not found"
        )
        await interaction.response.send_message(msg, ephemeral=True)

    @alerts.command(name="twitch-list", description="list twitch streamer alerts")
    async def twitch_list(self, interaction: discord.Interaction) -> None:
        if not isinstance(interaction.user, discord.Member) or not _is_admin(
            interaction.user
        ):
            await interaction.response.send_message(
                "missing permissions", ephemeral=True
            )
            return
        if interaction.guild is None:
            return
        entries = await get_streamer_alerts(self.bot.db, interaction.guild.id, "twitch")
        if not entries:
            await interaction.response.send_message(
                "no twitch alerts configured", ephemeral=True
            )
            return
        lines = ["**twitch alerts:**"]
        for streamer, channel_id, msg in entries:
            preview = (
                f" — `{msg[:40]}...`"
                if msg and len(msg) > 40
                else (f" — `{msg}`" if msg else "")
            )
            lines.append(f"- **{streamer}** → <#{channel_id}>{preview}")
        await interaction.response.send_message("\n".join(lines), ephemeral=True)

    @alerts.command(name="youtube-add", description="add a youtube channel alert")
    @app_commands.describe(
        channel_id="youtube channel id",
        channel="discord channel to post alerts in",
        message="custom message ({channel}, {title}, {url})",
    )
    async def youtube_add(
        self,
        interaction: discord.Interaction,
        channel_id: str,
        channel: discord.TextChannel,
        message: str | None = None,
    ) -> None:
        if not isinstance(interaction.user, discord.Member) or not _is_admin(
            interaction.user
        ):
            await interaction.response.send_message(
                "missing permissions", ephemeral=True
            )
            return
        if interaction.guild is None:
            return
        await upsert_streamer_alert(
            self.bot.db,
            interaction.guild.id,
            "youtube",
            channel_id,
            channel.id,
            message,
        )
        await interaction.response.send_message(
            f"youtube alert added for `{channel_id}` → {channel.mention}",
            ephemeral=True,
        )

    @alerts.command(name="youtube-remove", description="remove a youtube channel alert")
    @app_commands.describe(channel_id="youtube channel id")
    async def youtube_remove(
        self,
        interaction: discord.Interaction,
        channel_id: str,
    ) -> None:
        if not isinstance(interaction.user, discord.Member) or not _is_admin(
            interaction.user
        ):
            await interaction.response.send_message(
                "missing permissions", ephemeral=True
            )
            return
        if interaction.guild is None:
            return
        removed = await delete_streamer_alert(
            self.bot.db, interaction.guild.id, "youtube", channel_id
        )
        msg = (
            f"removed youtube alert for `{channel_id}`"
            if removed
            else "alert not found"
        )
        await interaction.response.send_message(msg, ephemeral=True)

    @alerts.command(name="youtube-list", description="list youtube channel alerts")
    async def youtube_list(self, interaction: discord.Interaction) -> None:
        if not isinstance(interaction.user, discord.Member) or not _is_admin(
            interaction.user
        ):
            await interaction.response.send_message(
                "missing permissions", ephemeral=True
            )
            return
        if interaction.guild is None:
            return
        entries = await get_streamer_alerts(
            self.bot.db, interaction.guild.id, "youtube"
        )
        if not entries:
            await interaction.response.send_message(
                "no youtube alerts configured", ephemeral=True
            )
            return
        lines = ["**youtube alerts:**"]
        for yt_id, channel_id, msg in entries:
            preview = (
                f" — `{msg[:40]}...`"
                if msg and len(msg) > 40
                else (f" — `{msg}`" if msg else "")
            )
            lines.append(f"- `{yt_id}` → <#{channel_id}>{preview}")
        await interaction.response.send_message("\n".join(lines), ephemeral=True)


async def setup(bot: "Bot") -> None:
    await bot.add_cog(AlertsCog(bot))
