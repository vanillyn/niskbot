from __future__ import annotations

from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from src.member.util import _is_admin
from src.server.resources import render_resource, store_buttons, update_msg_id
from src.utils.logger import get_logger
from src.utils.placeholders import (
    action_needs_admin,
    parse_buttons,
    resolve_text,
)

if TYPE_CHECKING:
    from src.bot import Bot

log = get_logger("echo")


class EchoCog(commands.Cog, name="echo"):
    def __init__(self, bot: "Bot") -> None:
        self.bot = bot

    @app_commands.command(name="echo", description="send a message to a channel")
    @app_commands.describe(message="message content", channel="channel to send to")
    async def echo(
        self,
        interaction: discord.Interaction,
        message: str,
        channel: discord.TextChannel | None = None,
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

        target = channel
        if target is None:
            if not isinstance(interaction.channel, discord.TextChannel):
                await interaction.response.send_message(
                    "run in a text channel or specify one", ephemeral=True
                )
                return
            target = interaction.channel

        guild = interaction.guild
        member = interaction.user

        check = parse_buttons(resolve_text(message, guild, member, target))
        for b in check.buttons.values():
            if not b.is_link and action_needs_admin(b.action):
                if not member.guild_permissions.administrator:
                    await interaction.response.send_message(
                        f"button `{b.name}` uses admin-only placeholders",
                        ephemeral=True,
                    )
                    return

        is_plain = (
            all(seg.kind == "text" for seg in check.segments) and not check.buttons
        )

        await interaction.response.defer(ephemeral=True)

        if is_plain:
            plain = "\n".join(seg.value for seg in check.segments)
            await target.send(content=plain)
            await interaction.followup.send(f"sent to {target.mention}", ephemeral=True)
            return

        layout, non_link = await render_resource(
            self.bot.db, guild.id, message, guild, member, target
        )
        await store_buttons(self.bot.db, guild.id, non_link)
        msg = await target.send(view=layout)
        if non_link:
            await update_msg_id(self.bot.db, [b.internal_id for b in non_link], msg.id)
        await interaction.followup.send(f"sent to {target.mention}", ephemeral=True)
        log.info("echo sent to %s in guild %s", target.id, guild.id)


async def setup(bot: "Bot") -> None:
    await bot.add_cog(EchoCog(bot))
