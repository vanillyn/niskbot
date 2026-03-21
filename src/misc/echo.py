from __future__ import annotations

from typing import TYPE_CHECKING

import discord
from discord import app_commands, ui
from discord.ext import commands

from src.member.util import _is_admin
from src.server.resources import render_resource, store_buttons, update_msg_id
from src.utils.logger import get_logger
from src.utils.placeholders import action_needs_admin, parse_buttons, resolve_text

if TYPE_CHECKING:
    from src.bot import Bot

log = get_logger("echo")


class _EchoModal(ui.Modal, title="echo content"):
    content_field: ui.TextInput["_EchoModal"] = ui.TextInput(
        label="content",
        custom_id="content",
        style=discord.TextStyle.paragraph,
        max_length=2000,
        required=True,
    )

    def __init__(self, channel: discord.TextChannel) -> None:
        super().__init__()
        self._channel = channel

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None or not isinstance(
            interaction.user, discord.Member
        ):
            return
        from src.bot import Bot

        bot = interaction.client
        if not isinstance(bot, Bot):
            return
        text = self.content_field.value
        guild = interaction.guild
        member = interaction.user
        channel = self._channel

        parsed = parse_buttons(resolve_text(text, guild, member, channel))
        for b in parsed.buttons:
            if not b.is_link and action_needs_admin(b.action):
                if not member.guild_permissions.administrator:
                    await interaction.response.send_message(
                        f"button `{b.name}` uses admin-only placeholders",
                        ephemeral=True,
                    )
                    return

        await interaction.response.defer(ephemeral=True)
        layout, non_link = await render_resource(
            bot.db, guild.id, text, guild, member, channel
        )
        await store_buttons(bot.db, guild.id, non_link)
        msg = await channel.send(view=layout)
        if non_link:
            await update_msg_id(bot.db, [b.internal_id for b in non_link], msg.id)
        await interaction.followup.send(f"sent to {channel.mention}", ephemeral=True)
        log.info("echo sent to channel %s in guild %s", channel.id, guild.id)

    async def on_error(
        self, interaction: discord.Interaction, error: Exception
    ) -> None:
        log.error("echo modal error: %s", error)
        if not interaction.response.is_done():
            await interaction.response.send_message(
                "something went wrong", ephemeral=True
            )


class EchoCog(commands.Cog, name="echo"):
    def __init__(self, bot: "Bot") -> None:
        self.bot = bot

    @app_commands.command(
        name="echo", description="send a message with placeholder support"
    )
    @app_commands.describe(channel="channel to send to")
    async def echo(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
    ) -> None:
        if not isinstance(interaction.user, discord.Member) or not _is_admin(
            interaction.user
        ):
            await interaction.response.send_message(
                "missing permissions", ephemeral=True
            )
            return
        await interaction.response.send_modal(_EchoModal(channel))


async def setup(bot: "Bot") -> None:
    await bot.add_cog(EchoCog(bot))
