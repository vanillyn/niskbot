from __future__ import annotations

import functools
import os
import time
from datetime import datetime
from typing import TYPE_CHECKING

import discord
from discord import app_commands, ui
from discord.ext import commands, tasks

from src.data.config import GuildConfig
from src.data.util import (
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
from src.web.apis.twitch import (
    eventsub_list,
    eventsub_subscribe,
    eventsub_unsubscribe,
    get_follower_count,
    get_stream,
    get_user,
)
from src.web.apis.youtube import YouTubeClient
from src.web.server import webhook as _webhook

if TYPE_CHECKING:
    from src.bot import Bot

log = get_logger("alerts")

_YOUTUBE_INTERVAL = 300
_CALLBACK_URL: str = ""


def set_callback_url(url: str) -> None:
    global _CALLBACK_URL
    _CALLBACK_URL = url


def _twitch_callback_url() -> str:
    return f"{_CALLBACK_URL}/webhook/twitch"


async def _render_resource_alert(
    bot: "Bot",
    guild: discord.Guild,
    resource_name: str,
    substitutions: dict[str, str],
    member: discord.Member | None = None,
    channel: discord.TextChannel | None = None,
) -> BaseLayout | None:
    row = await bot.db.fetchone(
        "select content from resources where guild_id = ? and name = ?",
        (guild.id, resource_name),
    )
    if row is None:
        return None
    content = str(row[0])
    for k, v in substitutions.items():
        content = content.replace(k, v)
    if member is None:
        if bot.user is None:
            return None
        member = guild.get_member(bot.user.id)
        if member is None:
            return None
    from src.server.resources import render_resource

    layout, _ = await render_resource(bot.db, guild.id, content, guild, member, channel)
    return layout


async def _send_member_alert(
    bot: "Bot",
    guild: discord.Guild,
    member: discord.Member,
    channel: discord.TextChannel,
    template: str,
    accent: int,
) -> None:
    if template.startswith("resource:"):
        resource_name = template[9:].strip()
        layout = await _render_resource_alert(
            bot, guild, resource_name, {}, member, channel
        )
        if layout is not None:
            try:
                await channel.send(view=layout)
            except discord.HTTPException as e:
                log.error("member alert resource send failed in %s: %s", guild.id, e)
            return
    text = resolve_text(template, guild, member, channel)
    plain_layout = BaseLayout()
    plain_layout.add_container(ui.TextDisplay(text), accent_color=accent)
    try:
        await channel.send(view=plain_layout)
    except discord.HTTPException as e:
        log.error("member alert send failed in %s: %s", guild.id, e)


async def _handle_stream_online(bot: "Bot", broadcaster_id: str) -> None:
    from src.data.db import Database

    assert isinstance(bot.db, Database)

    user = await get_user(user_id=broadcaster_id)
    stream = await get_stream(broadcaster_id)
    followers = await get_follower_count(broadcaster_id)

    display_name = str(user["display_name"]) if user else broadcaster_id
    profile_pic = str(user["profile_image_url"]) if user else ""
    stream_title = stream["title"] if stream else "untitled stream"
    game = stream["game_name"] if stream else "unknown"
    thumbnail_url = (
        stream["thumbnail_url"].replace("{width}", "1280").replace("{height}", "720")
        if stream
        else profile_pic
    )
    stream_url = f"https://twitch.tv/{display_name.lower()}"

    relative_ts = ""
    if stream and stream.get("started_at"):
        started = datetime.fromisoformat(
            str(stream["started_at"]).replace("Z", "+00:00")
        )
        relative_ts = f"<t:{int(started.timestamp())}:R>"

    subs: dict[str, str] = {
        "{streamer}": display_name,
        "{title}": stream_title,
        "{game}": game,
        "{url}": stream_url,
        "{followers}": f"{followers:,}",
    }

    for guild in bot.guilds:
        entries = await get_streamer_alerts(bot.db, guild.id, "twitch")
        for streamer_login, channel_id, message in entries:
            user_info = await get_user(login=streamer_login)
            if not user_info or str(user_info.get("id", "")) != broadcaster_id:
                continue

            channel = guild.get_channel(channel_id)
            if not isinstance(channel, discord.TextChannel):
                continue

            if message is not None and message.startswith("resource:"):
                resource_name = message[9:].strip()
                layout = await _render_resource_alert(
                    bot, guild, resource_name, subs, None, channel
                )
                if layout is not None:
                    try:
                        await channel.send(view=layout)
                        log.info(
                            "sent resource twitch alert for %s in guild %s",
                            display_name,
                            guild.id,
                        )
                    except discord.HTTPException as e:
                        log.error("twitch resource alert failed: %s", e)
                    continue

            cfg = await GuildConfig.load(bot.db, guild.id)
            template = message or f"{display_name} is live!"
            text = template
            for k, v in subs.items():
                text = text.replace(k, v)

            container = discord.ui.Container(
                discord.ui.Section(
                    discord.ui.TextDisplay(
                        f"# {text}\n[{stream_title}]({stream_url})\nplaying **{game}**"
                    ),
                    accessory=discord.ui.Thumbnail(media=profile_pic),
                ),
                discord.ui.MediaGallery(
                    discord.MediaGalleryItem(media=thumbnail_url),
                ),
                discord.ui.TextDisplay(
                    f"-# {followers:,} followers{' | ' + relative_ts if relative_ts else ''}"
                ),
                discord.ui.ActionRow(
                    discord.ui.Button(
                        label="watch live",
                        url=stream_url,
                        style=discord.ButtonStyle.link,
                    )
                ),
                accent_color=discord.Color(0x9146FF),
            )
            fallback = BaseLayout()
            fallback.add_item(container)
            try:
                await channel.send(view=fallback)
                log.info("sent live alert for %s in guild %s", display_name, guild.id)
            except discord.HTTPException as e:
                log.error("failed to send live alert: %s", e)
            _ = cfg


async def _send_youtube_alert(
    bot: "Bot",
    guild: discord.Guild,
    channel: discord.TextChannel,
    yt_channel_id: str,
    stream: dict[str, object],
    message: str | None,
) -> None:
    channel_title = str(stream.get("channel_title", yt_channel_id))
    title = str(stream.get("title", ""))
    url = str(stream.get("url", ""))

    subs: dict[str, str] = {
        "{channel}": channel_title,
        "{title}": title,
        "{url}": url,
    }

    if message is not None and message.startswith("resource:"):
        resource_name = message[9:].strip()
        layout = await _render_resource_alert(
            bot, guild, resource_name, subs, None, channel
        )
        if layout is not None:
            try:
                await channel.send(view=layout)
            except discord.HTTPException as e:
                log.error("youtube resource alert failed in guild %s: %s", guild.id, e)
            return

    text = message or f"{channel_title} is live on youtube!"
    for k, v in subs.items():
        text = text.replace(k, v)

    layout = BaseLayout()
    layout.add_container(
        ui.TextDisplay(f"**{text}**\n[{title}]({url})"),
        accent_color=0xFF0000,
    )
    try:
        await channel.send(view=layout)
    except discord.HTTPException as e:
        log.error("youtube alert failed in guild %s: %s", guild.id, e)


async def _ensure_subscription(broadcaster_id: str) -> str | None:
    existing = await eventsub_list()
    for sub in existing:
        cond = sub.get("condition", {})
        if (
            isinstance(cond, dict)
            and cond.get("broadcaster_user_id") == broadcaster_id
            and sub.get("type") == "stream.online"
            and sub.get("status") == "enabled"
        ):
            return str(sub["id"])
    return await eventsub_subscribe(broadcaster_id, _twitch_callback_url())


async def _remove_subscription_if_unused(
    bot: "Bot", broadcaster_id: str, sub_id: str
) -> None:
    from src.data.db import Database

    assert isinstance(bot.db, Database)
    for guild in bot.guilds:
        entries = await get_streamer_alerts(bot.db, guild.id, "twitch")
        for streamer_login, _, _ in entries:
            user_info = await get_user(login=streamer_login)
            if user_info and str(user_info.get("id", "")) == broadcaster_id:
                return
    await eventsub_unsubscribe(sub_id)
    log.info("removed eventsub subscription %s (no guilds need it)", sub_id)


class AlertsCog(commands.Cog, name="alerts"):
    def __init__(self, bot: "Bot") -> None:
        self.bot = bot
        self._youtube: YouTubeClient | None = None
        yt_key = os.environ.get("YOUTUBE_API_KEY", "")
        if yt_key:
            self._youtube = YouTubeClient(yt_key)

    async def cog_load(self) -> None:
        await self._sync_eventsub()
        if self._youtube is not None:
            self._check_youtube.start()

    async def cog_unload(self) -> None:
        self._check_youtube.cancel()
        if self._youtube is not None:
            await self._youtube.close()

    async def _sync_eventsub(self) -> None:
        if not _CALLBACK_URL:
            log.warning("no callback url set — skipping eventsub sync")
            return

        needed: set[str] = set()
        for guild in self.bot.guilds:
            entries = await get_streamer_alerts(self.bot.db, guild.id, "twitch")
            for streamer_login, _, _ in entries:
                user_info = await get_user(login=streamer_login)
                if user_info:
                    needed.add(str(user_info["id"]))

        callback = functools.partial(_handle_stream_online, self.bot)
        for broadcaster_id in needed:
            sub_id = await _ensure_subscription(broadcaster_id)
            if sub_id:
                _webhook.register(broadcaster_id, callback)
                log.info("eventsub active for %s", broadcaster_id)

    @tasks.loop(seconds=_YOUTUBE_INTERVAL)
    async def _check_youtube(self) -> None:
        if self._youtube is None:
            return
        now = int(time.time())
        for guild in self.bot.guilds:
            entries = await get_streamer_alerts(self.bot.db, guild.id, "youtube")
            for yt_id, discord_channel_id, message in entries:
                try:
                    stream = await self._youtube.get_live_stream(yt_id)
                except Exception as e:
                    log.error("youtube api error for %s: %s", yt_id, e)
                    continue
                is_live = stream is not None
                was_live = await get_stream_cache(
                    self.bot.db, guild.id, "youtube", yt_id
                )
                await set_stream_cache(
                    self.bot.db, guild.id, "youtube", yt_id, is_live, now
                )
                if not is_live or was_live:
                    continue
                channel = guild.get_channel(discord_channel_id)
                if not isinstance(channel, discord.TextChannel):
                    continue
                assert stream is not None
                await _send_youtube_alert(
                    self.bot, guild, channel, yt_id, stream, message
                )

    @_check_youtube.before_loop
    async def _before_youtube(self) -> None:
        await self.bot.wait_until_ready()

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
        await _send_member_alert(self.bot, guild, member, channel, template, 0x57F287)

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
        await _send_member_alert(self.bot, guild, member, channel, template, 0xED4245)

    alerts = app_commands.Group(name="alerts", description="manage streamer alerts")

    @alerts.command(name="twitch-add", description="add a twitch streamer alert")
    @app_commands.describe(
        streamer="twitch username",
        channel="channel to post alerts in",
        message="custom message or resource:name ({streamer}, {title}, {game}, {url}, {followers})",
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

        await interaction.response.defer(ephemeral=True)

        user_info = await get_user(login=streamer.lower())
        if user_info is None:
            await interaction.followup.send(
                f"couldn't find twitch user `{streamer}`", ephemeral=True
            )
            return

        broadcaster_id = str(user_info["id"])
        await upsert_streamer_alert(
            self.bot.db,
            interaction.guild.id,
            "twitch",
            streamer.lower(),
            channel.id,
            message,
        )

        sub_id = await _ensure_subscription(broadcaster_id)
        if sub_id:
            callback = functools.partial(_handle_stream_online, self.bot)
            _webhook.register(broadcaster_id, callback)
            log.info("eventsub subscribed for %s (%s)", streamer, broadcaster_id)
        else:
            log.warning("eventsub subscription failed for %s", streamer)

        await interaction.followup.send(
            f"twitch alert added for **{user_info['display_name']}** → {channel.mention}",
            ephemeral=True,
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

        await interaction.response.defer(ephemeral=True)

        removed = await delete_streamer_alert(
            self.bot.db, interaction.guild.id, "twitch", streamer.lower()
        )
        if not removed:
            await interaction.followup.send("alert not found", ephemeral=True)
            return

        user_info = await get_user(login=streamer.lower())
        if user_info:
            broadcaster_id = str(user_info["id"])
            existing = await eventsub_list()
            for sub in existing:
                cond = sub.get("condition", {})
                if (
                    isinstance(cond, dict)
                    and cond.get("broadcaster_user_id") == broadcaster_id
                ):
                    await _remove_subscription_if_unused(
                        self.bot, broadcaster_id, str(sub["id"])
                    )
                    break

        await interaction.followup.send(
            f"removed twitch alert for **{streamer}**", ephemeral=True
        )

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
                f" — `{msg[:40]}{'...' if len(msg or '') > 40 else ''}`" if msg else ""
            )
            lines.append(f"- **{streamer}** → <#{channel_id}>{preview}")
        await interaction.response.send_message("\n".join(lines), ephemeral=True)

    @alerts.command(name="youtube-add", description="add a youtube channel alert")
    @app_commands.describe(
        channel_id="youtube channel id",
        channel="discord channel to post alerts in",
        message="custom message or resource:name ({channel}, {title}, {url})",
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
                f" — `{msg[:40]}{'...' if len(msg or '') > 40 else ''}`" if msg else ""
            )
            lines.append(f"- `{yt_id}` → <#{channel_id}>{preview}")
        await interaction.response.send_message("\n".join(lines), ephemeral=True)


async def setup(bot: "Bot") -> None:
    await bot.add_cog(AlertsCog(bot))
