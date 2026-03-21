from __future__ import annotations

from typing import TYPE_CHECKING

import discord
from discord import app_commands, ui
from discord.ext import commands

from src.data.config import delete_config, get_all_config, set_config
from src.data.util import _CONFIGS, _CONFIGS_FLAT
from src.member.util import _is_admin
from src.utils.ui import BaseLayout

if TYPE_CHECKING:
    from src.bot import Bot


def _display(raw: str | None, default: str | None) -> str:
    if raw is not None:
        trimmed = raw if len(raw) <= 60 else raw[:60] + "..."
        return f"`{trimmed}`"
    if default is not None:
        return f"{default} *(default)*"
    return "*not set*"


class _CatSelect(ui.Select["_ConfigView"]):
    def __init__(self, parent: "_ConfigView") -> None:
        self._bot = parent._bot
        self._guild_id = parent._guild_id
        options = [
            discord.SelectOption(
                label=cat, value=cat, default=(cat == parent._category)
            )
            for cat in _CONFIGS
        ]
        super().__init__(placeholder="category", options=options)

    async def callback(self, interaction: discord.Interaction) -> None:
        vals = await get_all_config(self._bot.db, self._guild_id)
        view = _ConfigView(self._bot, self._guild_id, vals, self.values[0])
        await interaction.response.edit_message(view=view)


class _KeySelect(ui.Select["_ConfigView"]):
    def __init__(self, parent: "_ConfigView") -> None:
        self._bot = parent._bot
        self._guild_id = parent._guild_id
        self._category = parent._category
        self._selected_key = parent._selected_key
        entries = _CONFIGS[parent._category]
        options = [
            discord.SelectOption(
                label=label[:25],
                description=_display(parent._values.get(key), default)[:100],
                value=key,
                default=(key == parent._selected_key),
            )
            for key, label, _hint, default in entries
        ]
        super().__init__(placeholder="pick a setting to edit", options=options)

    async def callback(self, interaction: discord.Interaction) -> None:
        vals = await get_all_config(self._bot.db, self._guild_id)
        view = _ConfigView(
            self._bot,
            self._guild_id,
            vals,
            self._category,
            selected_key=self.values[0],
        )
        await interaction.response.edit_message(view=view)


class _SetButton(ui.Button["_ConfigView"]):
    def __init__(self, parent: "_ConfigView") -> None:
        self._bot = parent._bot
        self._guild_id = parent._guild_id
        self._category = parent._category
        self._selected_key = parent._selected_key
        self._values = parent._values
        super().__init__(
            label="set",
            style=discord.ButtonStyle.primary,
            disabled=parent._selected_key is None,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        key = self._selected_key
        if key is None:
            return
        label, hint, _default = _CONFIGS_FLAT[key]
        current = self._values.get(key, "")
        await interaction.response.send_modal(
            _SetModal(
                self._bot,
                self._guild_id,
                self._category,
                key,
                label,
                hint,
                current,
            )
        )


class _UnsetButton(ui.Button["_ConfigView"]):
    def __init__(self, parent: "_ConfigView") -> None:
        self._bot = parent._bot
        self._guild_id = parent._guild_id
        self._category = parent._category
        self._selected_key = parent._selected_key
        super().__init__(
            label="unset",
            style=discord.ButtonStyle.danger,
            disabled=parent._selected_key is None,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        key = self._selected_key
        if key is None:
            return
        await delete_config(self._bot.db, self._guild_id, key)
        vals = await get_all_config(self._bot.db, self._guild_id)
        view = _ConfigView(self._bot, self._guild_id, vals, self._category, key)
        await interaction.response.edit_message(view=view)


class _ConfigView(BaseLayout):
    def __init__(
        self,
        bot: "Bot",
        guild_id: int,
        values: dict[str, str],
        category: str,
        selected_key: str | None = None,
    ) -> None:
        super().__init__(timeout=300)
        self._bot = bot
        self._guild_id = guild_id
        self._values = values
        self._category = category
        self._selected_key = selected_key
        self._render()

    def _render(self) -> None:
        entries = _CONFIGS[self._category]
        lines: list[str] = [f"## {self._category}\n"]
        for key, label, _hint, default in entries:
            marker = "**›** " if key == self._selected_key else ""
            lines.append(
                f"{marker}**{label}** — {_display(self._values.get(key), default)}"
            )
        self.add_container(ui.TextDisplay("\n".join(lines)))

        if self._selected_key is not None and self._selected_key in _CONFIGS_FLAT:
            sel_label, sel_hint, sel_default = _CONFIGS_FLAT[self._selected_key]
            detail = f"**editing: {sel_label}**\nformat: {sel_hint}"
            if sel_default:
                detail += f"\ndefault: {sel_default}"
            self.add_container(ui.TextDisplay(detail), accent_color=0x5865F2)

        self.add_sep()
        self.add_item(ui.ActionRow(_CatSelect(self)))
        self.add_item(ui.ActionRow(_KeySelect(self)))
        self.add_item(ui.ActionRow(_SetButton(self), _UnsetButton(self)))


class _SetModal(ui.Modal):
    def __init__(
        self,
        bot: "Bot",
        guild_id: int,
        category: str,
        key: str,
        label: str,
        hint: str,
        current: str,
    ) -> None:
        super().__init__(title=f"set: {label}"[:45], custom_id=f"cfg:{key}"[:100])
        self._bot = bot
        self._guild_id = guild_id
        self._category = category
        self._key = key
        self._field = ui.TextInput(
            label=label[:45],
            custom_id="v",
            placeholder=hint[:100],
            default=current or None,
            required=False,
            max_length=500,
            style=discord.TextStyle.paragraph,
        )
        self.add_item(self._field)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        val = self._field.value.strip()
        if val:
            await set_config(self._bot.db, self._guild_id, self._key, val)
        vals = await get_all_config(self._bot.db, self._guild_id)
        view = _ConfigView(self._bot, self._guild_id, vals, self._category, self._key)
        if interaction.message is not None:
            await interaction.message.edit(view=view)
        msg = f"updated **{self._key}**" if val else "no change made"
        await interaction.response.send_message(msg, ephemeral=True)

    async def on_error(
        self, interaction: discord.Interaction, error: Exception
    ) -> None:
        await interaction.response.send_message("something went wrong", ephemeral=True)
        raise error


class ConfigCog(commands.Cog, name="config"):
    def __init__(self, bot: "Bot") -> None:
        self.bot = bot

    @app_commands.command(name="config", description="browse and edit server settings")
    async def config_cmd(self, interaction: discord.Interaction) -> None:
        if not isinstance(interaction.user, discord.Member) or not _is_admin(
            interaction.user
        ):
            await interaction.response.send_message(
                "missing permissions", ephemeral=True
            )
            return
        if interaction.guild is None:
            return
        vals = await get_all_config(self.bot.db, interaction.guild.id)
        first_cat = next(iter(_CONFIGS))
        view = _ConfigView(self.bot, interaction.guild.id, vals, first_cat)
        await interaction.response.send_message(view=view, ephemeral=True)


async def setup(bot: "Bot") -> None:
    await bot.add_cog(ConfigCog(bot))
