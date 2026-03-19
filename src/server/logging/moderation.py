from __future__ import annotations

import discord
from discord import ui

from src.data.configs import get_config
from src.data.db import Database
from src.server.moderation.infractions import Infraction
from src.utils.ui import BaseLayout


def _infraction_layout(
    infraction: Infraction,
    moderator: discord.Member | None,
) -> BaseLayout:
    mod_str = str(moderator) if moderator is not None else str(infraction.moderator_id)
    lines = [
        f"**{infraction.type}** — case `{infraction.case_str}`",
        f"**target:** {infraction.target_name} (`{infraction.target_id}`)",
        f"**moderator:** {mod_str}",
        f"**reason:** {infraction.reason}",
        f"**issued:** <t:{infraction.created_at}:R>",
    ]
    if infraction.duration is not None:
        expires = infraction.created_at + infraction.duration
        lines.append(f"**expires:** <t:{expires}:R>")

    layout = BaseLayout()
    layout.add_container(
        ui.TextDisplay("\n".join(lines)),
        accent_color=0xED4245,
    )
    return layout


async def log_infraction(
    db: Database,
    guild: discord.Guild,
    infraction: Infraction,
) -> None:
    raw = await get_config(db, guild.id, "mod_log_channel")
    if raw is None:
        return
    channel = guild.get_channel(int(raw))
    if not isinstance(channel, discord.TextChannel):
        return
    moderator = guild.get_member(infraction.moderator_id)
    layout = _infraction_layout(infraction, moderator)
    await channel.send(view=layout)
