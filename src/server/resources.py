from __future__ import annotations

import re
import time
from typing import TYPE_CHECKING

import discord
from discord import app_commands, ui
from discord.ext import commands

from src.member.util import _is_admin
from src.server.containers import build_discord_container
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

log = get_logger("resources")


async def _get_resource(
    db: object, guild_id: int, name: str
) -> tuple[int, str, int] | None:
    from src.data.db import Database

    assert isinstance(db, Database)
    row = await db.fetchone(
        "select id, content, creator_id from resources where guild_id = ? and name = ?",
        (guild_id, name),
    )
    if row is None:
        return None
    return int(row[0]), str(row[1]), int(row[2])  # type: ignore[arg-type]


async def _save_resource(
    db: object, guild_id: int, name: str, creator_id: int, content: str
) -> None:
    from src.data.db import Database

    assert isinstance(db, Database)
    await db.execute(
        "insert into resources (guild_id, name, creator_id, content, created_at)"
        " values (?, ?, ?, ?, ?)"
        " on conflict (guild_id, name) do update set content = excluded.content",
        (guild_id, name, creator_id, content, int(time.time())),
    )


async def _delete_resource(db: object, guild_id: int, name: str) -> None:
    from src.data.db import Database

    assert isinstance(db, Database)
    await db.execute(
        "delete from resources where guild_id = ? and name = ?",
        (guild_id, name),
    )


async def _list_resources(db: object, guild_id: int) -> list[str]:
    from src.data.db import Database

    assert isinstance(db, Database)
    rows = await db.fetchall(
        "select name from resources where guild_id = ? order by name",
        (guild_id,),
    )
    return [str(r[0]) for r in rows]


async def store_buttons(db: object, guild_id: int, buttons: list[ParsedButton]) -> None:
    from src.data.db import Database

    assert isinstance(db, Database)
    for b in buttons:
        if b.is_link:
            continue
        await db.execute(
            "insert or ignore into resource_buttons"
            " (button_uuid, guild_id, button_name, button_label, button_style, disabled, action)"
            " values (?, ?, ?, ?, ?, ?, ?)",
            (
                b.internal_id,
                guild_id,
                b.name,
                b.label,
                b.style.name.lower(),
                int(b.disabled),
                b.action,
            ),
        )


async def update_msg_id(db: object, button_uuids: list[str], message_id: int) -> None:
    from src.data.db import Database

    assert isinstance(db, Database)
    for uuid in button_uuids:
        await db.execute(
            "update resource_buttons set message_id = ? where button_uuid = ?",
            (message_id, uuid),
        )


class ResourceButton(ui.DynamicItem[ui.Button[ui.View]], template=r"rb:([a-f0-9-]+)"):
    def __init__(
        self,
        button_uuid: str,
        label: str,
        style: discord.ButtonStyle,
        disabled: bool,
    ) -> None:
        item: ui.Button[ui.View] = ui.Button(
            label=label,
            style=style,
            disabled=disabled,
            custom_id=f"rb:{button_uuid}",
        )
        super().__init__(item)
        self._uuid = button_uuid

    @classmethod
    async def from_custom_id(
        cls,
        interaction: discord.Interaction,
        item: ui.Button[ui.View],
        match: re.Match[str],
    ) -> "ResourceButton":
        return cls(match.group(1), item.label or "button", item.style, item.disabled)

    async def callback(self, interaction: discord.Interaction) -> None:
        from src.bot import Bot

        bot = interaction.client
        if not isinstance(bot, Bot):
            return
        row = await bot.db.fetchone(
            "select action from resource_buttons where button_uuid = ?",
            (self._uuid,),
        )
        if row is None:
            await interaction.response.send_message("button not found", ephemeral=True)
            return
        from src.utils.placeholders import execute_action

        await execute_action(interaction, str(row[0]))


async def render_resource(
    db: object,
    guild_id: int,
    content: str,
    guild: discord.Guild,
    member: discord.Member,
    channel: discord.abc.GuildChannel | discord.Thread | None = None,
    mentions: list[discord.Member] | None = None,
) -> tuple[BaseLayout, list[ParsedButton]]:
    from src.data.db import Database

    assert isinstance(db, Database)

    resolved = resolve_text(content, guild, member, channel, mentions)
    parsed = parse_buttons(resolved)

    layout = BaseLayout()
    non_link: list[ParsedButton] = []
    seen: set[str] = set()

    def _make_btn(btn_def: ParsedButton) -> ui.Button[ui.View]:
        if btn_def.is_link and btn_def.url:
            return ui.Button(
                label=btn_def.label,
                url=btn_def.url,
                style=discord.ButtonStyle.link,
            )
        btn: ui.Button[ui.View] = ui.Button(
            label=btn_def.label,
            style=btn_def.style,
            disabled=btn_def.disabled,
            custom_id=f"rb:{btn_def.internal_id}",
        )
        if btn_def.internal_id not in seen:
            seen.add(btn_def.internal_id)
            non_link.append(btn_def)
        return btn

    displayed_names: set[str] = set()

    for seg in parsed.segments:
        if seg.kind == "text":
            layout.add_container(ui.TextDisplay(seg.value))
        elif seg.kind == "separator":
            layout.add_sep()
        elif seg.kind == "container":
            row = await db.fetchone(
                "select items, accent_color from containers"
                " where guild_id = ? and name = ?",
                (guild_id, seg.value),
            )
            if row is not None:
                layout.add_item(
                    build_discord_container(
                        str(row[0]),
                        int(row[1]) if row[1] is not None else None,
                    )
                )
        elif seg.kind == "display":
            ids = [i.strip() for i in seg.value.split(",") if i.strip()]
            btns: list[ui.Button[ui.View]] = []
            for btn_id in ids:
                displayed_names.add(btn_id)
                btn_def = parsed.buttons.get(btn_id)
                if btn_def is not None:
                    btns.append(_make_btn(btn_def))
            if btns:
                action_row: ui.ActionRow[BaseLayout] = ui.ActionRow(*btns[:5])
                layout.add_item(action_row)

    undisplayed = [b for n, b in parsed.buttons.items() if n not in displayed_names]
    if undisplayed:
        all_btns = [_make_btn(b) for b in undisplayed]
        for i in range(0, len(all_btns), 5):
            layout.add_item(ui.ActionRow(*all_btns[i : i + 5]))

    return layout, non_link


async def _resource_autocomplete(
    interaction: discord.Interaction,
    current: str,
) -> list[app_commands.Choice[str]]:
    if interaction.guild is None:
        return []
    from src.bot import Bot

    bot = interaction.client
    if not isinstance(bot, Bot):
        return []
    names = await _list_resources(bot.db, interaction.guild.id)
    return [
        app_commands.Choice(name=n, value=n)
        for n in names
        if current.lower() in n.lower()
    ][:25]


class _CreateModal(ui.Modal, title="resource content"):
    content_field: ui.TextInput["_CreateModal"] = ui.TextInput(
        label="content",
        custom_id="content",
        style=discord.TextStyle.paragraph,
        max_length=2000,
        required=True,
    )

    def __init__(self, name: str, current: str = "") -> None:
        super().__init__()
        self._name = name
        self.content_field.default = current or None

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None or not isinstance(
            interaction.user, discord.Member
        ):
            return
        from src.bot import Bot

        bot = interaction.client
        if not isinstance(bot, Bot):
            return
        await _save_resource(
            bot.db,
            interaction.guild.id,
            self._name,
            interaction.user.id,
            self.content_field.value,
        )
        await interaction.response.send_message(f"saved `{self._name}`", ephemeral=True)
        log.info("resource %s saved in guild %s", self._name, interaction.guild.id)

    async def on_error(
        self, interaction: discord.Interaction, error: Exception
    ) -> None:
        log.error("resource modal error: %s", error)
        if not interaction.response.is_done():
            await interaction.response.send_message(
                "something went wrong", ephemeral=True
            )


class ResourceCog(commands.Cog, name="resources"):
    def __init__(self, bot: "Bot") -> None:
        self.bot = bot

    resource = app_commands.Group(
        name="resource", description="manage server resources"
    )

    @resource.command(name="create", description="create or overwrite a resource")
    @app_commands.describe(name="resource name")
    async def create(self, interaction: discord.Interaction, name: str) -> None:
        if not isinstance(interaction.user, discord.Member) or not _is_admin(
            interaction.user
        ):
            await interaction.response.send_message(
                "missing permissions", ephemeral=True
            )
            return
        if interaction.guild is None:
            return
        name = name.lower().replace(" ", "-")
        existing = await _get_resource(self.bot.db, interaction.guild.id, name)
        modal = _CreateModal(name, existing[1] if existing else "")
        await interaction.response.send_modal(modal)

    @resource.command(name="send", description="send a resource to a channel")
    @app_commands.describe(name="resource name", channel="target channel")
    @app_commands.autocomplete(name=_resource_autocomplete)
    async def send(
        self,
        interaction: discord.Interaction,
        name: str,
        channel: discord.TextChannel,
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
        row = await _get_resource(self.bot.db, interaction.guild.id, name)
        if row is None:
            await interaction.response.send_message(
                f"resource `{name}` not found", ephemeral=True
            )
            return
        _, content, _ = row
        check = parse_buttons(
            resolve_text(content, interaction.guild, interaction.user, channel)
        )
        for b in check.buttons.values():
            if not b.is_link and action_needs_admin(b.action):
                if not interaction.user.guild_permissions.administrator:
                    await interaction.response.send_message(
                        f"button `{b.name}` uses admin-only placeholders",
                        ephemeral=True,
                    )
                    return
        await interaction.response.defer(ephemeral=True)
        layout, non_link = await render_resource(
            self.bot.db,
            interaction.guild.id,
            content,
            interaction.guild,
            interaction.user,
            channel,
        )
        await store_buttons(self.bot.db, interaction.guild.id, non_link)
        msg = await channel.send(view=layout)
        if non_link:
            await update_msg_id(self.bot.db, [b.internal_id for b in non_link], msg.id)
        await interaction.followup.send(f"sent to {channel.mention}", ephemeral=True)
        log.info(
            "resource %s sent to channel %s in guild %s",
            name,
            channel.id,
            interaction.guild.id,
        )

    @resource.command(name="preview", description="preview a resource (ephemeral)")
    @app_commands.describe(name="resource name")
    @app_commands.autocomplete(name=_resource_autocomplete)
    async def preview(self, interaction: discord.Interaction, name: str) -> None:
        if not isinstance(interaction.user, discord.Member) or not _is_admin(
            interaction.user
        ):
            await interaction.response.send_message(
                "missing permissions", ephemeral=True
            )
            return
        if interaction.guild is None:
            return
        row = await _get_resource(self.bot.db, interaction.guild.id, name)
        if row is None:
            await interaction.response.send_message(
                f"resource `{name}` not found", ephemeral=True
            )
            return
        _, content, _ = row
        await interaction.response.defer(ephemeral=True)
        layout, _ = await render_resource(
            self.bot.db,
            interaction.guild.id,
            content,
            interaction.guild,
            interaction.user,
        )
        await interaction.followup.send(view=layout, ephemeral=True)

    @resource.command(name="delete", description="delete a resource")
    @app_commands.describe(name="resource name")
    @app_commands.autocomplete(name=_resource_autocomplete)
    async def delete(self, interaction: discord.Interaction, name: str) -> None:
        if not isinstance(interaction.user, discord.Member) or not _is_admin(
            interaction.user
        ):
            await interaction.response.send_message(
                "missing permissions", ephemeral=True
            )
            return
        if interaction.guild is None:
            return
        row = await _get_resource(self.bot.db, interaction.guild.id, name)
        if row is None:
            await interaction.response.send_message(
                f"resource `{name}` not found", ephemeral=True
            )
            return
        await _delete_resource(self.bot.db, interaction.guild.id, name)
        await interaction.response.send_message(f"deleted `{name}`", ephemeral=True)

    @resource.command(name="list", description="list all resources")
    async def list_cmd(self, interaction: discord.Interaction) -> None:
        if not isinstance(interaction.user, discord.Member) or not _is_admin(
            interaction.user
        ):
            await interaction.response.send_message(
                "missing permissions", ephemeral=True
            )
            return
        if interaction.guild is None:
            return
        names = await _list_resources(self.bot.db, interaction.guild.id)
        if not names:
            await interaction.response.send_message("no resources yet", ephemeral=True)
            return
        await interaction.response.send_message(
            "**resources:**\n" + "\n".join(f"- `{n}`" for n in names),
            ephemeral=True,
        )


async def setup(bot: "Bot") -> None:
    await bot.add_cog(ResourceCog(bot))
