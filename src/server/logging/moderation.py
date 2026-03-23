from __future__ import annotations

import random

import discord
from discord import ui

from src.data.config import GuildConfig
from src.data.db import Database
from src.server.moderation.infractions import Infraction
from src.utils.logger import get_logger
from src.utils.ui import BaseLayout

_logger = get_logger(__name__)


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
        _logger.debug(
            f"Moderation logging disabled or channel not set. "
            f"moderation_enabled={cfg.log.moderation} "
            f"channel_id={cfg.log.moderation_channel}"
        )
        return
    channel = guild.get_channel(cfg.log.moderation_channel)
    if not isinstance(channel, discord.TextChannel):
        _logger.warning(
            f"Moderation log channel {cfg.log.moderation_channel} not found or not a text channel"
        )
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
    try:
        await channel.send(view=layout)
    except discord.HTTPException as e:
        _logger.warning(
            f"Failed to send moderation log to channel {cfg.log.moderation_channel}: {e}"
        )
        # Fallback: try to notify the guild owner so the failure is visible
        owner = guild.owner
        if owner is not None:
            try:
                await owner.send(
                    f"Failed to post moderation log in #{getattr(channel, 'name', str(channel.id))} ({getattr(channel, 'id', 'unknown')}) for guild {guild.name}:\n{e}"
                )
            except discord.HTTPException:
                _logger.exception(
                    "Failed to DM guild owner about moderation logging failure"
                )
        return
    except Exception:
        _logger.exception("Unexpected error while sending moderation log")
        return

    _logger.info(
        f"Infraction logged: case={infraction.case_str} type={infraction.type} "
        f"user={infraction.target_name} moderator={infraction.moderator_id}"
    )
