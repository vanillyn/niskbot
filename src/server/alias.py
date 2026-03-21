from __future__ import annotations

from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from src.data.config import GuildConfig
from src.data.db import Database
from src.server.permissions import has_permission

if TYPE_CHECKING:
    from src.bot import Bot


async def _get(db: Database, guild_id: int, name: str) -> str | None:
    row = await db.fetchone(
        "select response from aliases where guild_id = ? and name = ?",
        (guild_id, name),
    )
    return str(row[0]) if row is not None else None


async def _set(db: Database, guild_id: int, name: str, response: str) -> None:
    await db.execute(
        "insert into aliases (guild_id, name, response) values (?, ?, ?)"
        " on conflict (guild_id, name) do update set response = excluded.response",
        (guild_id, name, response),
    )


async def _delete(db: Database, guild_id: int, name: str) -> bool:
    row = await db.fetchone(
        "select 1 from aliases where guild_id = ? and name = ?",
        (guild_id, name),
    )
    if row is None:
        return False
    await db.execute(
        "delete from aliases where guild_id = ? and name = ?",
        (guild_id, name),
    )
    return True


async def _list(db: Database, guild_id: int) -> list[tuple[str, str]]:
    rows = await db.fetchall(
        "select name, response from aliases where guild_id = ? order by name",
        (guild_id,),
    )
    return [(str(r[0]), str(r[1])) for r in rows]


async def _can_manage(db: Database, member: discord.Member) -> bool:
    if member.guild_permissions.administrator:
        return True
    return await has_permission(db, member, "commands.alias.permission")


class AliasCog(commands.Cog, name="alias"):
    def __init__(self, bot: "Bot") -> None:
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot:
            return
        if not isinstance(message.guild, discord.Guild):
            return
        if not isinstance(message.channel, discord.TextChannel):
            return
        cfg = await GuildConfig.load(self.bot.db, message.guild.id)
        if not cfg.server.alias:
            return
        prefix = cfg.server.alias_prefix
        if not message.content.startswith(prefix):
            return
        parts = message.content[len(prefix) :].strip().split()
        if not parts:
            return
        name = parts[0].lower()
        response = await _get(self.bot.db, message.guild.id, name)
        if response is None:
            return
        await message.channel.send(response)

    alias = app_commands.Group(name="alias", description="manage server aliases")

    @alias.command(name="add", description="add or update an alias")
    @app_commands.describe(
        name="alias name (no spaces)", response="what the alias sends"
    )
    async def add(
        self,
        interaction: discord.Interaction,
        name: str,
        response: str,
    ) -> None:
        if (
            not isinstance(interaction.user, discord.Member)
            or interaction.guild is None
        ):
            return
        if not await _can_manage(self.bot.db, interaction.user):
            await interaction.response.send_message(
                "missing permissions", ephemeral=True
            )
            return
        await _set(self.bot.db, interaction.guild.id, name.lower().strip(), response)
        await interaction.response.send_message(
            f"alias `{name.lower()}` saved", ephemeral=True
        )

    @alias.command(name="remove", description="remove an alias")
    @app_commands.describe(name="alias name")
    async def remove(
        self,
        interaction: discord.Interaction,
        name: str,
    ) -> None:
        if (
            not isinstance(interaction.user, discord.Member)
            or interaction.guild is None
        ):
            return
        if not await _can_manage(self.bot.db, interaction.user):
            await interaction.response.send_message(
                "missing permissions", ephemeral=True
            )
            return
        removed = await _delete(self.bot.db, interaction.guild.id, name.lower())
        msg = f"alias `{name}` removed" if removed else f"alias `{name}` not found"
        await interaction.response.send_message(msg, ephemeral=True)

    @alias.command(name="list", description="list all aliases")
    async def list_cmd(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            return
        entries = await _list(self.bot.db, interaction.guild.id)
        if not entries:
            await interaction.response.send_message(
                "no aliases configured", ephemeral=True
            )
            return
        lines = ["**aliases:**"]
        for name, response in entries:
            preview = response[:60] + "..." if len(response) > 60 else response
            lines.append(f"`{name}` — {preview}")
        await interaction.response.send_message("\n".join(lines), ephemeral=True)


async def setup(bot: "Bot") -> None:
    await bot.add_cog(AliasCog(bot))
