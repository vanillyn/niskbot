from __future__ import annotations

import random

import discord
from discord import ui

from src.data.config import GuildConfig
from src.data.db import Database
from src.server.moderation.infractions import Infraction
from src.utils.ui import BaseLayout


def _resolve(
    template: str, infraction: Infraction, moderator: discord.Member | None
) -> str:
    mod_str = str(moderator) if moderator is not None else str(infraction.moderator_id)
    expires = (
        f"<t:{infraction.created_at + infraction.duration}:R>"
        if infraction.duration is not None
        else "permanent"
    )
    return (
        template.replace("{infraction_id}", infraction.case_str)
        .replace("{user}", infraction.target_name)
        .replace("{moderator}", mod_str)
        .replace("{reason}", infraction.reason)
        .replace("{duration}", expires)
    )


async def log_infraction(
    db: Database, guild: discord.Guild, infraction: Infraction
) -> None:
    cfg = await GuildConfig.load(db, guild.id)
    if not cfg.log.moderation or cfg.log.moderation_channel is None:
        return
    channel = guild.get_channel(cfg.log.moderation_channel)
    if not isinstance(channel, discord.TextChannel):
        return

    templates: dict[str, list[str]] = {
        "kick": cfg.log.msg_kick,
        "ban": cfg.log.msg_ban,
        "mute": cfg.log.msg_mute,
        "warn": cfg.log.msg_warn,
        "slowmode": cfg.log.msg_slowmode,
    }
    moderator = guild.get_member(infraction.moderator_id)
    header = _resolve(
        random.choice(templates.get(infraction.type, [infraction.type])),
        infraction,
        moderator,
    )

    lines: list[str] = [header]
    if cfg.log.moderation_show_moderator:
        mod_str = (
            str(moderator) if moderator is not None else str(infraction.moderator_id)
        )
        lines.append(f"**moderator:** {mod_str}")
    if cfg.log.moderation_show_reason:
        lines.append(f"**reason:** {infraction.reason}")
    if infraction.duration is not None:
        lines.append(
            f"**expires:** <t:{infraction.created_at + infraction.duration}:R>"
        )

    layout = BaseLayout()
    layout.add_container(ui.TextDisplay("\n".join(lines)), accent_color=0xED4245)
    await channel.send(view=layout)
