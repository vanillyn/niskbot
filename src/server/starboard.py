from __future__ import annotations

from typing import TYPE_CHECKING

import discord
from discord import ui
from discord.ext import commands

from src.data.config import GuildConfig
from src.data.db import Database
from src.utils.ui import BaseLayout

if TYPE_CHECKING:
    from src.bot import Bot

_EMOJI_ALIASES: dict[str, str] = {
    "star": "\u2b50",
}

_IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".gif", ".webp")


async def _has_entry(db: Database, guild_id: int, source_id: int) -> bool:
    row = await db.fetchone(
        "select 1 from starboard_entries where guild_id = ? and source_message_id = ?",
        (guild_id, source_id),
    )
    return row is not None


async def _add_entry(
    db: Database, guild_id: int, source_id: int, starboard_id: int
) -> None:
    await db.execute(
        "insert or ignore into starboard_entries"
        " (guild_id, source_message_id, starboard_message_id) values (?, ?, ?)",
        (guild_id, source_id, starboard_id),
    )


def _emoji_matches(emoji: discord.PartialEmoji, target: str) -> bool:
    resolved = _EMOJI_ALIASES.get(target, target)
    if emoji.is_custom_emoji():
        return emoji.name == resolved or emoji.name == target
    return str(emoji) == resolved or emoji.name == resolved


class StarboardCog(commands.Cog, name="starboard"):
    def __init__(self, bot: "Bot") -> None:
        self.bot = bot

    @commands.Cog.listener()
    async def on_raw_reaction_add(
        self, payload: discord.RawReactionActionEvent
    ) -> None:
        if payload.guild_id is None:
            return
        guild = self.bot.get_guild(payload.guild_id)
        if guild is None:
            return

        cfg = await GuildConfig.load(self.bot.db, guild.id)
        if cfg.server.starboard_channel is None:
            return
        if not _emoji_matches(payload.emoji, cfg.server.starboard_react):
            return
        if await _has_entry(self.bot.db, guild.id, payload.message_id):
            return

        source_ch = guild.get_channel(payload.channel_id)
        if not isinstance(source_ch, discord.TextChannel):
            return

        starboard_ch = guild.get_channel(cfg.server.starboard_channel)
        if not isinstance(starboard_ch, discord.TextChannel):
            return

        if source_ch.id == starboard_ch.id:
            return

        try:
            message = await source_ch.fetch_message(payload.message_id)
        except discord.HTTPException:
            return

        layout = BaseLayout()
        lines = [
            f"**{message.author.display_name}** in {source_ch.mention}",
        ]
        if message.content:
            lines.append(message.content)
        lines.append(f"[jump to message]({message.jump_url})")

        images = [
            a
            for a in message.attachments
            if any(a.filename.lower().endswith(ext) for ext in _IMAGE_EXTS)
        ]

        layout.add_container(ui.TextDisplay("\n".join(lines)), accent_color=0xFEE75C)

        if images:
            gallery_items = [discord.MediaGalleryItem(media=a.url) for a in images[:4]]
            layout.add_gallery(*gallery_items)

        try:
            sb_msg = await starboard_ch.send(view=layout)
        except discord.HTTPException:
            return

        await _add_entry(self.bot.db, guild.id, payload.message_id, sb_msg.id)


async def setup(bot: "Bot") -> None:
    await bot.add_cog(StarboardCog(bot))
