from __future__ import annotations

import discord
from discord import app_commands

from src.server.permissions import has_permission


class missing_moderation_permission(app_commands.CheckFailure):
    def __init__(self, node: str) -> None:
        self.node = node
        super().__init__(f"missing permission node: {node}")


class hierarchy_violation(app_commands.CheckFailure):
    def __init__(self) -> None:
        super().__init__("target has an equal or higher role")


def require_permission(node: str) -> "app_commands.check":
    async def predicate(interaction: discord.Interaction) -> bool:
        member = interaction.user
        if not isinstance(member, discord.Member):
            raise missing_moderation_permission(node)
        if member.guild_permissions.administrator:
            return True

        from src.bot import Bot

        bot = interaction.client
        if not isinstance(bot, Bot):
            raise missing_moderation_permission(node)

        allowed = await has_permission(bot.db, member, node)
        if not allowed:
            raise missing_moderation_permission(node)
        return True

    return app_commands.check(predicate)


def check_hierarchy(target: discord.Member, moderator: discord.Member) -> None:
    if target.top_role >= moderator.top_role:
        raise hierarchy_violation()