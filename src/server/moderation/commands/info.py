from __future__ import annotations

from typing import TYPE_CHECKING

import discord
from discord import app_commands, ui
from discord.ext import commands

from src.member.statistics.apis import get_last_message, get_name_history
from src.server.moderation.infractions import get_infractions
from src.server.permissions import has_permission
from src.utils.ui import BaseLayout

if TYPE_CHECKING:
    from src.bot import Bot


class InfoCog(commands.Cog, name="modinfo"):
    def __init__(self, bot: "Bot") -> None:
        self.bot = bot

    @app_commands.command(
        name="userinfo", description="view detailed info about a member"
    )
    @app_commands.describe(user="member to inspect")
    async def userinfo(
        self,
        interaction: discord.Interaction,
        user: discord.Member | None = None,
    ) -> None:
        if (
            not isinstance(interaction.user, discord.Member)
            or interaction.guild is None
        ):
            return
        if not await has_permission(self.bot.db, interaction.user, "moderation.info"):
            await interaction.response.send_message(
                "missing permissions", ephemeral=True
            )
            return
        target: discord.Member = user if user is not None else interaction.user

        name_history = await get_name_history(
            self.bot.db, interaction.guild.id, target.id
        )
        last_msg = await get_last_message(self.bot.db, interaction.guild.id, target.id)
        infractions = await get_infractions(
            self.bot.db, interaction.guild.id, target.id
        )

        lines: list[str] = [
            f"## {target.display_name}",
            f"**username** {target.name}",
            f"**display name** {target.display_name}",
            f"**id** `{target.id}`",
            f"**account created** <t:{int(target.created_at.timestamp())}:F>",
        ]
        if target.joined_at is not None:
            lines.append(f"**joined** <t:{int(target.joined_at.timestamp())}:F>")
        if last_msg is not None:
            ch_id, _, ts = last_msg
            lines.append(f"**last message** <t:{ts}:R> in <#{ch_id}>")
        else:
            lines.append("**last message** not recorded yet")
        lines.append(f"**infractions** {len(infractions)}")

        seen: set[tuple[str, str]] = set()
        deduped: list[tuple[str, str, int]] = []
        for uname, dname, ts in name_history:
            key = (uname, dname)
            if key not in seen:
                seen.add(key)
                deduped.append((uname, dname, ts))

        if deduped:
            lines.append("")
            lines.append("**name history**")
            for uname, dname, ts in deduped[:6]:
                lines.append(f"-# `{uname}` / {dname} — <t:{ts}:R>")

        layout = BaseLayout()
        layout.add_item(
            ui.Container(
                ui.Section(
                    ui.TextDisplay("\n".join(lines)),
                    accessory=ui.Thumbnail(media=target.display_avatar.url),
                )
            )
        )

        if infractions:
            layout.add_sep(large=True)
            inf_lines: list[str] = [
                f"**recent infractions** ({len(infractions)} total)"
            ]
            for inf in infractions[:8]:
                dur = ""
                if inf.duration is not None:
                    hrs = inf.duration // 3600
                    dur = f" · {hrs}h" if hrs > 0 else f" · {inf.duration}s"
                inf_lines.append(
                    f"`{inf.case_str}` **{inf.type}**{dur} — {inf.reason}\n"
                    f"-# <t:{inf.created_at}:d> · <@{inf.moderator_id}>"
                )
            if len(infractions) > 8:
                inf_lines.append(f"-# ...and {len(infractions) - 8} more")
            layout.add_container(
                ui.TextDisplay("\n".join(inf_lines)), accent_color=0xED4245
            )

        await interaction.response.send_message(view=layout, ephemeral=True)

    @app_commands.command(
        name="infractions", description="view all infractions for a member"
    )
    @app_commands.describe(user="member to inspect")
    async def infractions_cmd(
        self,
        interaction: discord.Interaction,
        user: discord.Member | None = None,
    ) -> None:
        if (
            not isinstance(interaction.user, discord.Member)
            or interaction.guild is None
        ):
            return
        if not await has_permission(self.bot.db, interaction.user, "moderation.info"):
            await interaction.response.send_message(
                "missing permissions", ephemeral=True
            )
            return
        target: discord.Member = user if user is not None else interaction.user

        infractions = await get_infractions(
            self.bot.db, interaction.guild.id, target.id
        )
        layout = BaseLayout()

        if not infractions:
            layout.add_container(
                ui.TextDisplay(
                    f"no infractions on record for **{target.display_name}**"
                )
            )
            await interaction.response.send_message(view=layout, ephemeral=True)
            return

        lines: list[str] = [
            f"## {target.display_name} — {len(infractions)} infraction(s)"
        ]
        for inf in infractions:
            dur = ""
            if inf.duration is not None:
                hrs = inf.duration // 3600
                dur = f" · {hrs}h" if hrs > 0 else f" · {inf.duration}s"
            lines.append(
                f"**`{inf.case_str}`** {inf.type}{dur}\n"
                f"{inf.reason}\n"
                f"-# <t:{inf.created_at}:d> · <@{inf.moderator_id}>"
            )

        layout.add_container(ui.TextDisplay("\n".join(lines)), accent_color=0xED4245)
        await interaction.response.send_message(view=layout, ephemeral=True)


async def setup(bot: "Bot") -> None:
    await bot.add_cog(InfoCog(bot))
