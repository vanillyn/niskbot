from __future__ import annotations

import json
import time
from typing import TYPE_CHECKING

import discord
from discord import app_commands, ui
from discord.ext import commands

from src.member.util import _is_admin
from src.utils.logger import get_logger
from src.utils.ui import BaseLayout

if TYPE_CHECKING:
    from src.bot import Bot

log = get_logger("containers")


async def _get(db: object, guild_id: int, name: str) -> tuple[str, int | None] | None:
    from src.data.db import Database

    assert isinstance(db, Database)
    row = await db.fetchone(
        "select items, accent_color from containers where guild_id = ? and name = ?",
        (guild_id, name),
    )
    if row is None:
        return None
    return str(row[0]), int(row[1]) if row[1] is not None else None


async def _upsert(
    db: object,
    guild_id: int,
    name: str,
    creator_id: int,
    items: list[dict[str, object]],
    accent_color: int | None,
) -> None:
    from src.data.db import Database

    assert isinstance(db, Database)
    await db.execute(
        "insert into containers (guild_id, name, creator_id, items, accent_color, created_at)"
        " values (?, ?, ?, ?, ?, ?)"
        " on conflict (guild_id, name) do update set"
        " items = excluded.items, accent_color = excluded.accent_color",
        (guild_id, name, creator_id, json.dumps(items), accent_color, int(time.time())),
    )


async def _update_items(
    db: object, guild_id: int, name: str, items: list[dict[str, object]]
) -> None:
    from src.data.db import Database

    assert isinstance(db, Database)
    await db.execute(
        "update containers set items = ? where guild_id = ? and name = ?",
        (json.dumps(items), guild_id, name),
    )


async def _update_accent(
    db: object, guild_id: int, name: str, accent_color: int | None
) -> None:
    from src.data.db import Database

    assert isinstance(db, Database)
    await db.execute(
        "update containers set accent_color = ? where guild_id = ? and name = ?",
        (accent_color, guild_id, name),
    )


async def _delete(db: object, guild_id: int, name: str) -> None:
    from src.data.db import Database

    assert isinstance(db, Database)
    await db.execute(
        "delete from containers where guild_id = ? and name = ?",
        (guild_id, name),
    )


async def _list_all(db: object, guild_id: int) -> list[str]:
    from src.data.db import Database

    assert isinstance(db, Database)
    rows = await db.fetchall(
        "select name from containers where guild_id = ? order by name",
        (guild_id,),
    )
    return [str(r[0]) for r in rows]


def build_discord_container(
    items_json: str, accent_color: int | None
) -> ui.Container[BaseLayout]:
    items: list[dict[str, object]] = json.loads(items_json)
    container: ui.Container[BaseLayout] = ui.Container(accent_color=accent_color)
    for item in items:
        itype = str(item.get("type", ""))
        if itype == "text":
            container.add_item(ui.TextDisplay(str(item.get("content", ""))))
        elif itype == "sep":
            spacing = (
                discord.SeparatorSpacing.large
                if item.get("large")
                else discord.SeparatorSpacing.small
            )
            container.add_item(ui.Separator(spacing=spacing))
        elif itype == "gallery":
            raw: list[dict[str, object]] = item.get("items", [])  # type: ignore[assignment]
            gi = [
                discord.MediaGalleryItem(
                    media=str(g["url"]),
                    description=str(g.get("description") or "") or None,
                )
                for g in raw
                if g.get("url")
            ]
            if gi:
                container.add_item(ui.MediaGallery(*gi))
    return container


def _items_summary(items: list[dict[str, object]]) -> str:
    if not items:
        return "*(empty)*"
    lines: list[str] = []
    for i, item in enumerate(items, 1):
        itype = str(item.get("type", "?"))
        if itype == "text":
            preview = str(item.get("content", ""))[:50].replace("\n", " ")
            lines.append(f"`{i}.` text \u2014 {preview}")
        elif itype == "sep":
            size = "large" if item.get("large") else "small"
            lines.append(f"`{i}.` separator ({size})")
        elif itype == "gallery":
            raw_list: list[object] = item.get("items", [])  # type: ignore[assignment]
            lines.append(f"`{i}.` gallery ({len(raw_list)} image(s))")
    return "\n".join(lines)


async def _container_autocomplete(
    interaction: discord.Interaction,
    current: str,
) -> list[app_commands.Choice[str]]:
    if interaction.guild is None:
        return []
    from src.bot import Bot

    bot = interaction.client
    if not isinstance(bot, Bot):
        return []
    names = await _list_all(bot.db, interaction.guild.id)
    return [
        app_commands.Choice(name=n, value=n)
        for n in names
        if current.lower() in n.lower()
    ][:25]


class _ContainerEditView(BaseLayout):
    def __init__(
        self,
        bot: "Bot",
        guild_id: int,
        creator_id: int,
        name: str,
        items: list[dict[str, object]],
        accent_color: int | None,
    ) -> None:
        super().__init__(timeout=300)
        self._bot = bot
        self._guild_id = guild_id
        self._creator_id = creator_id
        self._name = name
        self._items: list[dict[str, object]] = list(items)
        self._accent_color = accent_color
        self._render()

    def _render(self) -> None:
        summary = _items_summary(self._items)
        accent_str = f"#{self._accent_color:06x}" if self._accent_color else "none"
        self.add_container(
            ui.TextDisplay(
                f"**{self._name}** \u2014 accent: `{accent_str}`\n\n{summary}"
            ),
            accent_color=self._accent_color,
        )
        self.add_sep()
        row1: ui.ActionRow["_ContainerEditView"] = ui.ActionRow(
            _AddTextBtn(self),
            _AddSepSmallBtn(self),
            _AddSepLargeBtn(self),
            _AddGalleryBtn(self),
        )
        self.add_item(row1)
        if self._items:
            row2: ui.ActionRow["_ContainerEditView"] = ui.ActionRow(
                _RemoveLastBtn(self),
                _ClearBtn(self),
                _SetAccentBtn(self),
            )
        else:
            row2 = ui.ActionRow(_SetAccentBtn(self))
        self.add_item(row2)

    async def _save(self) -> None:
        await _update_items(self._bot.db, self._guild_id, self._name, self._items)

    async def _refresh(self, interaction: discord.Interaction) -> None:
        await self._save()
        new_view = _ContainerEditView(
            self._bot,
            self._guild_id,
            self._creator_id,
            self._name,
            self._items,
            self._accent_color,
        )
        if interaction.type == discord.InteractionType.modal_submit:
            await interaction.response.defer()
            try:
                await interaction.edit_original_response(view=new_view)
            except discord.HTTPException as e:
                log.error(
                    "container refresh edit failed for %s in guild %s: %s",
                    self._name,
                    self._guild_id,
                    e,
                )
        else:
            try:
                await interaction.response.edit_message(view=new_view)
            except discord.HTTPException as e:
                log.error(
                    "container edit_message failed for %s in guild %s: %s",
                    self._name,
                    self._guild_id,
                    e,
                )


class _AddTextBtn(ui.Button["_ContainerEditView"]):
    def __init__(self, parent: "_ContainerEditView") -> None:
        super().__init__(label="add text", style=discord.ButtonStyle.primary)
        self._p = parent

    async def callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(_AddTextModal(self._p))


class _AddSepSmallBtn(ui.Button["_ContainerEditView"]):
    def __init__(self, parent: "_ContainerEditView") -> None:
        super().__init__(label="add sep", style=discord.ButtonStyle.secondary)
        self._p = parent

    async def callback(self, interaction: discord.Interaction) -> None:
        self._p._items.append({"type": "sep", "large": False})
        await self._p._refresh(interaction)


class _AddSepLargeBtn(ui.Button["_ContainerEditView"]):
    def __init__(self, parent: "_ContainerEditView") -> None:
        super().__init__(label="add sep (large)", style=discord.ButtonStyle.secondary)
        self._p = parent

    async def callback(self, interaction: discord.Interaction) -> None:
        self._p._items.append({"type": "sep", "large": True})
        await self._p._refresh(interaction)


class _AddGalleryBtn(ui.Button["_ContainerEditView"]):
    def __init__(self, parent: "_ContainerEditView") -> None:
        super().__init__(label="add gallery", style=discord.ButtonStyle.secondary)
        self._p = parent

    async def callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(_AddGalleryModal(self._p))


class _RemoveLastBtn(ui.Button["_ContainerEditView"]):
    def __init__(self, parent: "_ContainerEditView") -> None:
        super().__init__(label="remove last", style=discord.ButtonStyle.danger)
        self._p = parent

    async def callback(self, interaction: discord.Interaction) -> None:
        if self._p._items:
            self._p._items.pop()
        await self._p._refresh(interaction)


class _ClearBtn(ui.Button["_ContainerEditView"]):
    def __init__(self, parent: "_ContainerEditView") -> None:
        super().__init__(label="clear all", style=discord.ButtonStyle.danger)
        self._p = parent

    async def callback(self, interaction: discord.Interaction) -> None:
        self._p._items.clear()
        await self._p._refresh(interaction)


class _SetAccentBtn(ui.Button["_ContainerEditView"]):
    def __init__(self, parent: "_ContainerEditView") -> None:
        super().__init__(label="set accent", style=discord.ButtonStyle.secondary)
        self._p = parent

    async def callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(_SetAccentModal(self._p))


class _AddTextModal(ui.Modal, title="add text display"):
    content_field: ui.TextInput["_AddTextModal"] = ui.TextInput(
        label="text content",
        custom_id="content",
        style=discord.TextStyle.paragraph,
        max_length=2000,
        required=True,
    )

    def __init__(self, parent: "_ContainerEditView") -> None:
        super().__init__()
        self._p = parent

    async def on_submit(self, interaction: discord.Interaction) -> None:
        self._p._items.append({"type": "text", "content": self.content_field.value})
        await self._p._refresh(interaction)

    async def on_error(
        self, interaction: discord.Interaction, error: Exception
    ) -> None:
        log.error("container add text error: %s", error)
        if not interaction.response.is_done():
            await interaction.response.send_message(
                "something went wrong", ephemeral=True
            )


class _AddGalleryModal(ui.Modal, title="add gallery"):
    urls_field: ui.TextInput["_AddGalleryModal"] = ui.TextInput(
        label="image urls (one per line)",
        custom_id="urls",
        style=discord.TextStyle.paragraph,
        max_length=2000,
        required=True,
    )
    descs_field: ui.TextInput["_AddGalleryModal"] = ui.TextInput(
        label="descriptions (one per line, optional)",
        custom_id="descs",
        style=discord.TextStyle.paragraph,
        max_length=2000,
        required=False,
    )

    def __init__(self, parent: "_ContainerEditView") -> None:
        super().__init__()
        self._p = parent

    async def on_submit(self, interaction: discord.Interaction) -> None:
        urls = [u.strip() for u in self.urls_field.value.splitlines() if u.strip()]
        descs = [d.strip() for d in (self.descs_field.value or "").splitlines()]
        gi: list[dict[str, object]] = [
            {"url": url, "description": descs[i] if i < len(descs) else ""}
            for i, url in enumerate(urls)
        ]
        self._p._items.append({"type": "gallery", "items": gi})
        await self._p._refresh(interaction)

    async def on_error(
        self, interaction: discord.Interaction, error: Exception
    ) -> None:
        log.error("container add gallery error: %s", error)
        if not interaction.response.is_done():
            await interaction.response.send_message(
                "something went wrong", ephemeral=True
            )


class _SetAccentModal(ui.Modal, title="set accent color"):
    color_field: ui.TextInput["_SetAccentModal"] = ui.TextInput(
        label="hex color (e.g. ff5733) or empty to clear",
        custom_id="color",
        style=discord.TextStyle.short,
        max_length=7,
        required=False,
    )

    def __init__(self, parent: "_ContainerEditView") -> None:
        super().__init__()
        self._p = parent
        self.color_field.default = (
            f"{parent._accent_color:06x}" if parent._accent_color else None
        )

    async def on_submit(self, interaction: discord.Interaction) -> None:
        val = (self.color_field.value or "").strip().lstrip("#")
        if not val:
            self._p._accent_color = None
        else:
            try:
                self._p._accent_color = int(val, 16)
            except ValueError:
                await interaction.response.send_message(
                    "invalid hex color", ephemeral=True
                )
                return
        await _update_accent(
            self._p._bot.db, self._p._guild_id, self._p._name, self._p._accent_color
        )
        await self._p._refresh(interaction)

    async def on_error(
        self, interaction: discord.Interaction, error: Exception
    ) -> None:
        log.error("container accent error: %s", error)
        if not interaction.response.is_done():
            await interaction.response.send_message(
                "something went wrong", ephemeral=True
            )


class ContainerCog(commands.Cog, name="containers"):
    def __init__(self, bot: "Bot") -> None:
        self.bot = bot

    container = app_commands.Group(
        name="container", description="manage reusable containers"
    )

    @container.command(name="create", description="create a new container")
    @app_commands.describe(name="container name")
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
        await _upsert(
            self.bot.db, interaction.guild.id, name, interaction.user.id, [], None
        )
        view = _ContainerEditView(
            self.bot, interaction.guild.id, interaction.user.id, name, [], None
        )
        await interaction.response.send_message(view=view, ephemeral=True)
        log.info("container %s created in guild %s", name, interaction.guild.id)

    @container.command(name="edit", description="edit an existing container")
    @app_commands.describe(name="container name")
    @app_commands.autocomplete(name=_container_autocomplete)
    async def edit(self, interaction: discord.Interaction, name: str) -> None:
        if not isinstance(interaction.user, discord.Member) or not _is_admin(
            interaction.user
        ):
            await interaction.response.send_message(
                "missing permissions", ephemeral=True
            )
            return
        if interaction.guild is None:
            return
        result = await _get(self.bot.db, interaction.guild.id, name)
        if result is None:
            await interaction.response.send_message(
                f"container `{name}` not found", ephemeral=True
            )
            return
        items_json, accent = result
        items: list[dict[str, object]] = json.loads(items_json)
        row = await self.bot.db.fetchone(
            "select creator_id from containers where guild_id = ? and name = ?",
            (interaction.guild.id, name),
        )
        creator_id = int(row[0]) if row is not None else interaction.user.id  # type: ignore[arg-type]
        view = _ContainerEditView(
            self.bot, interaction.guild.id, creator_id, name, items, accent
        )
        await interaction.response.send_message(view=view, ephemeral=True)
        log.info("container %s edit opened in guild %s", name, interaction.guild.id)

    @container.command(name="preview", description="preview a container")
    @app_commands.describe(name="container name")
    @app_commands.autocomplete(name=_container_autocomplete)
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
        result = await _get(self.bot.db, interaction.guild.id, name)
        if result is None:
            await interaction.response.send_message(
                f"container `{name}` not found", ephemeral=True
            )
            return
        items_json, accent = result
        layout = BaseLayout()
        layout.add_item(build_discord_container(items_json, accent))
        await interaction.response.send_message(view=layout, ephemeral=True)

    @container.command(name="delete", description="delete a container")
    @app_commands.describe(name="container name")
    @app_commands.autocomplete(name=_container_autocomplete)
    async def delete_cmd(self, interaction: discord.Interaction, name: str) -> None:
        if not isinstance(interaction.user, discord.Member) or not _is_admin(
            interaction.user
        ):
            await interaction.response.send_message(
                "missing permissions", ephemeral=True
            )
            return
        if interaction.guild is None:
            return
        result = await _get(self.bot.db, interaction.guild.id, name)
        if result is None:
            await interaction.response.send_message(
                f"container `{name}` not found", ephemeral=True
            )
            return
        await _delete(self.bot.db, interaction.guild.id, name)
        await interaction.response.send_message(f"deleted `{name}`", ephemeral=True)
        log.info("container %s deleted in guild %s", name, interaction.guild.id)

    @container.command(name="list", description="list all containers")
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
        names = await _list_all(self.bot.db, interaction.guild.id)
        if not names:
            await interaction.response.send_message("no containers yet", ephemeral=True)
            return
        text = "**containers:**\n" + "\n".join(f"- `{n}`" for n in names)
        await interaction.response.send_message(text, ephemeral=True)


async def setup(bot: "Bot") -> None:
    await bot.add_cog(ContainerCog(bot))
