from __future__ import annotations

from typing import TYPE_CHECKING

import discord
from discord.ext import commands

from src.member.statistics.apis import record_last_message, record_name

if TYPE_CHECKING:
    from src.bot import Bot


class MemberTrackingCog(commands.Cog, name="member_tracking"):
    def __init__(self, bot: "Bot") -> None:
        self.bot = bot

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        await record_name(
            self.bot.db, member.guild.id, member.id, member.name, member.display_name
        )

    @commands.Cog.listener()
    async def on_member_update(
        self, before: discord.Member, after: discord.Member
    ) -> None:
        if before.name == after.name and before.display_name == after.display_name:
            return
        await record_name(
            self.bot.db, after.guild.id, after.id, after.name, after.display_name
        )

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot:
            return
        if not isinstance(message.guild, discord.Guild):
            return
        await record_last_message(
            self.bot.db,
            message.guild.id,
            message.author.id,
            message.channel.id,
            message.id,
        )


async def setup(bot: "Bot") -> None:
    await bot.add_cog(MemberTrackingCog(bot))
