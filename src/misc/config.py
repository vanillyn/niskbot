from __future__ import annotations

from typing import TYPE_CHECKING

import discord
from discord import app_commands, ui
from discord.ext import commands

from src.data.configs import delete_config, get_all_config, get_config, set_config
from src.utils.ui import BaseLayout, BaseModal, InputField

if TYPE_CHECKING:
    from src.bot import Bot


def _is_admin(member: discord.Member) -> bool:
    return (
        member.guild_permissions.administrator or member.guild_permissions.manage_guild
    )


class _SetConfigModal(BaseModal, title="set config"):
    key_field: InputField = InputField(
        label="key",
        custom_id="config_key",
        placeholder="e.g. mod_log_channel",
    )
    value_field: InputField = InputField(
        label="value",
        custom_id="config_value",
        placeholder="e.g. 123456789",
    )

    def __init__(self, bot: Bot) -> None:
        super().__init__(title="set config", custom_id="modal:config_set")
        self._bot = bot

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            return
        key = self.key_field.value.strip()
        value = self.value_field.value.strip()
        if not key or not value:
            await interaction.response.send_message(
                "key and value cannot be empty", ephemeral=True
            )
            return
        await set_config(self._bot.db, interaction.guild.id, key, value)

        layout = BaseLayout()
        layout.add_container(
            ui.TextDisplay(f"**config updated**\n`{key}` set to `{value}`"),
            accent_color=0x57F287,
        )
        await interaction.response.send_message(view=layout, ephemeral=True)


class ConfigCog(commands.Cog, name="config"):
    def __init__(self, bot: Bot) -> None:
        self.bot = bot

    grp = app_commands.Group(name="config", description="manage server configuration")

    @grp.command(name="set", description="set a config value")
    async def config_set(self, interaction: discord.Interaction) -> None:
        if not isinstance(interaction.user, discord.Member) or not _is_admin(
            interaction.user
        ):
            await interaction.response.send_message(
                "missing permissions", ephemeral=True
            )
            return
        await interaction.response.send_modal(_SetConfigModal(self.bot))

    @grp.command(name="get", description="get a config value")
    @app_commands.describe(key="config key")
    async def config_get(self, interaction: discord.Interaction, key: str) -> None:
        if not isinstance(interaction.user, discord.Member) or not _is_admin(
            interaction.user
        ):
            await interaction.response.send_message(
                "missing permissions", ephemeral=True
            )
            return
        if interaction.guild is None:
            return
        value = await get_config(self.bot.db, interaction.guild.id, key)

        layout = BaseLayout()
        if value is None:
            layout.add_container(
                ui.TextDisplay(f"`{key}` is not set"),
                accent_color=0xED4245,
            )
        else:
            layout.add_container(
                ui.TextDisplay(f"**`{key}`**\n{value}"),
                accent_color=0x5865F2,
            )
        await interaction.response.send_message(view=layout, ephemeral=True)

    @grp.command(name="unset", description="remove a config value")
    @app_commands.describe(key="config key")
    async def config_unset(self, interaction: discord.Interaction, key: str) -> None:
        if not isinstance(interaction.user, discord.Member) or not _is_admin(
            interaction.user
        ):
            await interaction.response.send_message(
                "missing permissions", ephemeral=True
            )
            return
        if interaction.guild is None:
            return
        await delete_config(self.bot.db, interaction.guild.id, key)

        layout = BaseLayout()
        layout.add_container(
            ui.TextDisplay(f"unset `{key}`"),
            accent_color=0xFEE75C,
        )
        await interaction.response.send_message(view=layout, ephemeral=True)

    @grp.command(name="list", description="list all config values")
    async def config_list(self, interaction: discord.Interaction) -> None:
        if not isinstance(interaction.user, discord.Member) or not _is_admin(
            interaction.user
        ):
            await interaction.response.send_message(
                "missing permissions", ephemeral=True
            )
            return
        if interaction.guild is None:
            return
        data = await get_all_config(self.bot.db, interaction.guild.id)

        layout = BaseLayout()
        if not data:
            layout.add_container(
                ui.TextDisplay("no config values set"),
                accent_color=0xED4245,
            )
        else:
            lines = [f"`{k}` — {v}" for k, v in sorted(data.items())]
            layout.add_container(
                ui.TextDisplay("**server config**\n" + "\n".join(lines)),
                accent_color=0x5865F2,
            )
        await interaction.response.send_message(view=layout, ephemeral=True)


async def setup(bot: Bot) -> None:
    await bot.add_cog(ConfigCog(bot))
