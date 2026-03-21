from __future__ import annotations

import re
import time
from typing import TYPE_CHECKING

import discord
from discord import app_commands, ui
from discord.ext import commands, tasks

from src.data.config import GuildConfig
from src.data.db import Database
from src.utils.ui import BaseLayout

if TYPE_CHECKING:
    from src.bot import Bot


def _parse_timeout(s: str) -> int:
    total = 0
    for raw_n, u in re.findall(r"(\d+)\s*([smhd])", s, re.IGNORECASE):
        n = int(raw_n)
        match u.lower():
            case "s":
                total += n
            case "m":
                total += n * 60
            case "h":
                total += n * 3600
            case "d":
                total += n * 86400
    return total if total > 0 else 86400


async def _create(
    db: Database,
    guild_id: int,
    channel_id: int,
    author_id: int,
    title: str,
    details: str,
) -> int:
    await db.execute(
        "insert into suggestions (guild_id, channel_id, author_id, title, details, created_at)"
        " values (?, ?, ?, ?, ?, ?)",
        (guild_id, channel_id, author_id, title, details, int(time.time())),
    )
    row = await db.fetchone("select last_insert_rowid()")
    assert row is not None
    return int(row[0])  # type: ignore[arg-type]


async def _set_message_id(db: Database, suggestion_id: int, message_id: int) -> None:
    await db.execute(
        "update suggestions set message_id = ? where id = ?",
        (message_id, suggestion_id),
    )


async def _get(db: Database, suggestion_id: int) -> tuple[object, ...] | None:
    return await db.fetchone(
        "select id, guild_id, channel_id, message_id, author_id, title, details,"
        " votes_up, votes_down, status, created_at from suggestions where id = ?",
        (suggestion_id,),
    )


async def _get_open(db: Database) -> list[tuple[object, ...]]:
    return await db.fetchall(
        "select id, guild_id, channel_id, message_id, author_id, title, details,"
        " votes_up, votes_down, status, created_at from suggestions where status = 'open'",
    )


async def _record_vote(
    db: Database, suggestion_id: int, user_id: int, direction: str
) -> tuple[int, int]:
    existing_row = await db.fetchone(
        "select vote from suggestion_votes where suggestion_id = ? and user_id = ?",
        (suggestion_id, user_id),
    )
    existing = str(existing_row[0]) if existing_row is not None else None

    if existing == direction:
        await db.execute(
            "delete from suggestion_votes where suggestion_id = ? and user_id = ?",
            (suggestion_id, user_id),
        )
        col = "votes_up" if direction == "up" else "votes_down"
        await db.execute(
            f"update suggestions set {col} = max(0, {col} - 1) where id = ?",
            (suggestion_id,),
        )
    elif existing is not None:
        await db.execute(
            "update suggestion_votes set vote = ? where suggestion_id = ? and user_id = ?",
            (direction, suggestion_id, user_id),
        )
        if direction == "up":
            await db.execute(
                "update suggestions set votes_up = votes_up + 1,"
                " votes_down = max(0, votes_down - 1) where id = ?",
                (suggestion_id,),
            )
        else:
            await db.execute(
                "update suggestions set votes_down = votes_down + 1,"
                " votes_up = max(0, votes_up - 1) where id = ?",
                (suggestion_id,),
            )
    else:
        await db.execute(
            "insert into suggestion_votes (suggestion_id, user_id, vote) values (?, ?, ?)",
            (suggestion_id, user_id, direction),
        )
        col = "votes_up" if direction == "up" else "votes_down"
        await db.execute(
            f"update suggestions set {col} = {col} + 1 where id = ?",
            (suggestion_id,),
        )

    result = await db.fetchone(
        "select votes_up, votes_down from suggestions where id = ?",
        (suggestion_id,),
    )
    assert result is not None
    return int(result[0]), int(result[1])  # type: ignore[arg-type]


async def _close(db: Database, suggestion_id: int, status: str) -> None:
    await db.execute(
        "update suggestions set status = ? where id = ?",
        (status, suggestion_id),
    )


def _build_layout(
    title: str,
    details: str,
    author_id: int,
    votes_up: int,
    votes_down: int,
    suggestion_id: int,
    label_up: str,
    label_down: str,
    label_cancel: str,
    *,
    closed_status: str = "",
) -> BaseLayout:
    total = votes_up + votes_down
    pct = f"{int(votes_up / total * 100)}%" if total > 0 else "no votes yet"
    lines = [
        f"**{title}**",
        details,
        "",
        f"by <@{author_id}> \u2014 {votes_up} for / {votes_down} against / {pct} approval",
    ]
    if closed_status:
        lines.append(f"\n**{closed_status}**")

    if closed_status in ("approved",):
        color = 0x57F287
    elif closed_status:
        color = 0xED4245
    else:
        color = 0x5865F2

    layout = BaseLayout()
    layout.add_container(ui.TextDisplay("\n".join(lines)), accent_color=color)

    if not closed_status:
        layout.add_sep()
        up: ui.Button[BaseLayout] = ui.Button(
            label=label_up,
            style=discord.ButtonStyle.success,
            custom_id=f"sv:up:{suggestion_id}",
        )
        down: ui.Button[BaseLayout] = ui.Button(
            label=label_down,
            style=discord.ButtonStyle.danger,
            custom_id=f"sv:down:{suggestion_id}",
        )
        cancel: ui.Button[BaseLayout] = ui.Button(
            label=label_cancel,
            style=discord.ButtonStyle.secondary,
            custom_id=f"sv:cancel:{suggestion_id}",
        )
        layout.add_item(ui.ActionRow(up, down, cancel))

    return layout


class SuggestionButton(
    ui.DynamicItem[ui.Button[ui.View]], template=r"sv:(up|down|cancel):(\d+)"
):
    def __init__(
        self, action: str, suggestion_id: int, item: ui.Button[ui.View]
    ) -> None:
        super().__init__(item)
        self._action = action
        self._suggestion_id = suggestion_id

    @classmethod
    async def from_custom_id(
        cls,
        interaction: discord.Interaction,
        item: ui.Button[ui.View],
        match: re.Match[str],
    ) -> "SuggestionButton":
        return cls(match.group(1), int(match.group(2)), item)

    async def callback(self, interaction: discord.Interaction) -> None:
        from src.bot import Bot

        bot = interaction.client
        if not isinstance(bot, Bot) or not isinstance(interaction.guild, discord.Guild):
            return

        row = await _get(bot.db, self._suggestion_id)
        if row is None:
            await interaction.response.send_message(
                "suggestion not found", ephemeral=True
            )
            return

        guild_id = int(row[1])  # type: ignore[arg-type]
        channel_id = int(row[2])  # type: ignore[arg-type]
        author_id = int(row[4])  # type: ignore[arg-type]
        title = str(row[5])
        details = str(row[6])
        votes_up = int(row[7])  # type: ignore[arg-type]
        votes_down = int(row[8])  # type: ignore[arg-type]
        status = str(row[9])

        if interaction.guild.id != guild_id:
            return

        if status != "open":
            await interaction.response.send_message(
                "this suggestion is already closed", ephemeral=True
            )
            return

        cfg = await GuildConfig.load(bot.db, guild_id)
        member = interaction.guild.get_member(interaction.user.id)
        if member is None:
            return

        if self._action == "cancel":
            if (
                interaction.user.id != author_id
                and not member.guild_permissions.administrator
            ):
                await interaction.response.send_message(
                    "missing permissions", ephemeral=True
                )
                return
            await _close(bot.db, self._suggestion_id, "cancelled")
            layout = _build_layout(
                title,
                details,
                author_id,
                votes_up,
                votes_down,
                self._suggestion_id,
                cfg.server.suggestions_vote_up,
                cfg.server.suggestions_vote_down,
                cfg.server.suggestions_vote_cancel,
                closed_status="cancelled",
            )
            await interaction.response.edit_message(view=layout)
            return

        vote_roles = cfg.server.suggestions_vote_roles
        if vote_roles and not member.guild_permissions.administrator:
            member_role_ids = {r.id for r in member.roles}
            allowed = any(
                rid.isdigit() and int(rid) in member_role_ids for rid in vote_roles
            )
            if not allowed:
                await interaction.response.send_message(
                    "you don't have permission to vote", ephemeral=True
                )
                return

        direction = "up" if self._action == "up" else "down"
        new_up, new_down = await _record_vote(
            bot.db, self._suggestion_id, interaction.user.id, direction
        )

        layout = _build_layout(
            title,
            details,
            author_id,
            new_up,
            new_down,
            self._suggestion_id,
            cfg.server.suggestions_vote_up,
            cfg.server.suggestions_vote_down,
            cfg.server.suggestions_vote_cancel,
        )
        await interaction.response.edit_message(view=layout)
        _ = channel_id


class SuggestionsCog(commands.Cog, name="suggestions"):
    def __init__(self, bot: "Bot") -> None:
        self.bot = bot
        self._check.start()

    async def cog_unload(self) -> None:
        self._check.cancel()

    @tasks.loop(minutes=5)
    async def _check(self) -> None:
        now = int(time.time())
        rows = await _get_open(self.bot.db)
        for row in rows:
            suggestion_id = int(row[0])  # type: ignore[arg-type]
            guild_id = int(row[1])  # type: ignore[arg-type]
            channel_id = int(row[2])  # type: ignore[arg-type]
            message_id = int(row[3]) if row[3] is not None else None  # type: ignore[arg-type]
            author_id = int(row[4])  # type: ignore[arg-type]
            title = str(row[5])
            details = str(row[6])
            votes_up = int(row[7])  # type: ignore[arg-type]
            votes_down = int(row[8])  # type: ignore[arg-type]
            created_at = int(row[10])  # type: ignore[arg-type]

            guild = self.bot.get_guild(guild_id)
            if guild is None:
                continue

            cfg = await GuildConfig.load(self.bot.db, guild_id)
            if now < created_at + _parse_timeout(cfg.server.suggestions_timeout):
                continue

            total = votes_up + votes_down
            if total == 0:
                closed_status = "not considered — no votes"
                approved = False
            else:
                up_pct = votes_up / total * 100
                down_pct = votes_down / total * 100
                if up_pct >= cfg.server.suggestions_threshold_approve:
                    closed_status = "approved"
                    approved = True
                elif down_pct >= cfg.server.suggestions_threshold_disapprove:
                    closed_status = "not considered"
                    approved = False
                else:
                    closed_status = "not considered — inconclusive"
                    approved = False

            await _close(
                self.bot.db, suggestion_id, "approved" if approved else "disapproved"
            )

            if message_id is not None:
                ch = guild.get_channel(channel_id)
                if isinstance(ch, discord.TextChannel):
                    try:
                        msg = await ch.fetch_message(message_id)
                        layout = _build_layout(
                            title,
                            details,
                            author_id,
                            votes_up,
                            votes_down,
                            suggestion_id,
                            cfg.server.suggestions_vote_up,
                            cfg.server.suggestions_vote_down,
                            cfg.server.suggestions_vote_cancel,
                            closed_status=closed_status,
                        )
                        await msg.edit(view=layout)
                    except discord.HTTPException:
                        pass

            if approved and cfg.log.moderation_channel is not None:
                mod_ch = guild.get_channel(cfg.log.moderation_channel)
                if isinstance(mod_ch, discord.TextChannel):
                    lines = [
                        "**suggestion approved**",
                        f"**title:** {title}",
                        f"**details:** {details}",
                        f"**by:** <@{author_id}>",
                        f"**votes:** {votes_up} for / {votes_down} against",
                    ]
                    layout = BaseLayout()
                    layout.add_container(
                        ui.TextDisplay("\n".join(lines)), accent_color=0x57F287
                    )
                    try:
                        await mod_ch.send(view=layout)
                    except discord.HTTPException:
                        pass

    @_check.before_loop
    async def _before_check(self) -> None:
        await self.bot.wait_until_ready()

    @app_commands.command(name="suggest", description="submit a suggestion")
    @app_commands.describe(title="suggestion title", details="details")
    async def suggest(
        self,
        interaction: discord.Interaction,
        title: str,
        details: str,
    ) -> None:
        if (
            not isinstance(interaction.user, discord.Member)
            or interaction.guild is None
        ):
            return

        cfg = await GuildConfig.load(self.bot.db, interaction.guild.id)
        if cfg.server.suggestions_channel is None:
            await interaction.response.send_message(
                "suggestions are not configured on this server", ephemeral=True
            )
            return

        channel = interaction.guild.get_channel(cfg.server.suggestions_channel)
        if not isinstance(channel, discord.TextChannel):
            await interaction.response.send_message(
                "suggestions channel not found", ephemeral=True
            )
            return

        suggestion_id = await _create(
            self.bot.db,
            interaction.guild.id,
            channel.id,
            interaction.user.id,
            title,
            details,
        )

        layout = _build_layout(
            title,
            details,
            interaction.user.id,
            0,
            0,
            suggestion_id,
            cfg.server.suggestions_vote_up,
            cfg.server.suggestions_vote_down,
            cfg.server.suggestions_vote_cancel,
        )

        try:
            msg = await channel.send(view=layout)
        except discord.HTTPException as e:
            await interaction.response.send_message(
                f"failed to send: {e}", ephemeral=True
            )
            return

        await _set_message_id(self.bot.db, suggestion_id, msg.id)
        await interaction.response.send_message(
            f"suggestion submitted to {channel.mention}", ephemeral=True
        )


async def setup(bot: "Bot") -> None:
    await bot.add_cog(SuggestionsCog(bot))
