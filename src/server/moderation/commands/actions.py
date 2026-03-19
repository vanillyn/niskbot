from __future__ import annotations

from typing import TYPE_CHECKING

import discord
from discord import app_commands, ui
from discord.ext import commands
from src.server.moderation.infractions import add_infraction

from src.server.logging.moderation import log_infraction
from src.server.permissions import has_permission
from src.utils.ui import BaseLayout

if TYPE_CHECKING:
    from src.bot import Bot


def _warn_layout(
    target: discord.Member,
    moderator: discord.Member,
    reason: str,
    case_str: str,
) -> BaseLayout:
    lines = [
        f"**warn** — case `{case_str}`",
        f"**user:** {target} (`{target.id}`)",
        f"**moderator:** {moderator}",
        f"**reason:** {reason}",
    ]
    layout = BaseLayout()
    layout.add_container(
        ui.TextDisplay("\n".join(lines)),
        accent_color=0xFEE75C,
    )
    return layout


class ModerationActionsCog(commands.Cog, name="moderation"):
    def __init__(self, bot: Bot) -> None:
        self.bot = bot

    @app_commands.command(name="warn", description="warn a member")
    @app_commands.describe(
        user="member to warn",
        reason="reason for the warning",
        quiet="only show the response to you",
    )
    async def warn(
        self,
        interaction: discord.Interaction,
        user: discord.Member,
        reason: str,
        quiet: bool = False,
    ) -> None:
        if interaction.guild is None:
            return
        if not isinstance(interaction.user, discord.Member):
            return
        if not await has_permission(self.bot.db, interaction.user, "moderation.warn"):
            await interaction.response.send_message(
                "missing permissions", ephemeral=True
            )
            return
        if user.top_role >= interaction.user.top_role:
            await interaction.response.send_message(
                "you cannot warn someone with an equal or higher role", ephemeral=True
            )
            return

        infraction = await add_infraction(
            self.bot.db,
            guild_id=interaction.guild.id,
            target_id=user.id,
            target_name=str(user),
            moderator_id=interaction.user.id,
            infraction_type="warn",
            reason=reason,
        )

        await log_infraction(self.bot.db, interaction.guild, infraction)

        layout = _warn_layout(user, interaction.user, reason, infraction.case_str)
        await interaction.response.send_message(view=layout, ephemeral=quiet)


async def setup(bot: Bot) -> None:
    await bot.add_cog(ModerationActionsCog(bot))
