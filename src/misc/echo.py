from __future__ import annotations

from typing import TYPE_CHECKING

import discord
from discord import app_commands, ui
from discord.ext import commands

from src.member.util import _is_admin
from src.server.containers import build_discord_container
from src.server.resources import store_buttons, update_msg_id
from src.utils.logger import get_logger
from src.utils.placeholders import (
    ParsedButton,
    action_needs_admin,
    parse_buttons,
    resolve_text,
)
from src.utils.ui import BaseLayout

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
        resolved = resolve_text(message, guild, member, target)
        parsed = parse_buttons(resolved)

        for b in parsed.buttons:
            if not b.is_link and action_needs_admin(b.action):
                if not member.guild_permissions.administrator:
                    await interaction.response.send_message(
                        f"button `{b.name}` uses admin-only placeholders",
                        ephemeral=True,
                    )
                    return

        await interaction.response.defer(ephemeral=True)

        has_containers = bool(parsed.container_refs)

        if not has_containers and not parsed.buttons:
            await target.send(content=parsed.text)
            await interaction.followup.send(f"sent to {target.mention}", ephemeral=True)
            return

        layout = BaseLayout()

        for cname in parsed.container_refs:
            row = await self.bot.db.fetchone(
                "select items, accent_color from containers where guild_id = ? and name = ?",
                (guild.id, cname),
            )
            if row is not None:
                layout.add_item(
                    build_discord_container(
                        str(row[0]),
                        int(row[1]) if row[1] is not None else None,  # type: ignore[arg-type]
                    )
                )

        if parsed.text:
            if has_containers:
                layout.add_container(ui.TextDisplay(parsed.text))
            else:
                layout.add_text(parsed.text)

        non_link: list[ParsedButton] = []
        all_btns: list[ui.Button[ui.View]] = []
        for b in parsed.buttons:
            if b.is_link and b.url:
                btn: ui.Button[ui.View] = ui.Button(
                    label=b.label, url=b.url, style=discord.ButtonStyle.link
                )
            else:
                btn = ui.Button(
                    label=b.label,
                    style=b.style,
                    disabled=b.disabled,
                    custom_id=f"rb:{b.internal_id}",
                )
                non_link.append(b)
            all_btns.append(btn)

        for i in range(0, len(all_btns), 5):
            action_row: ui.ActionRow[BaseLayout] = ui.ActionRow(*all_btns[i : i + 5])
            layout.add_item(action_row)

        await store_buttons(self.bot.db, guild.id, non_link)
        msg = await target.send(view=layout)
        if non_link:
            await update_msg_id(self.bot.db, [b.internal_id for b in non_link], msg.id)
        await interaction.followup.send(f"sent to {target.mention}", ephemeral=True)
        log.info("echo sent to %s in guild %s", target.id, guild.id)


async def setup(bot: "Bot") -> None:
    await bot.add_cog(EchoCog(bot))
