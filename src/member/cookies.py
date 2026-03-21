from __future__ import annotations

from typing import TYPE_CHECKING

import discord
from discord import app_commands, ui
from discord.ext import commands

from src.data.config import GuildConfig
from src.data.economy import (
    add_balance,
    add_cookies,
    get_cookies,
    subtract_cookies,
)
from src.utils.ui import BaseLayout

if TYPE_CHECKING:
    from src.bot import Bot


class CookiesCog(commands.Cog, name="cookies"):
    def __init__(self, bot: "Bot") -> None:
        self.bot = bot

    cookie = app_commands.Group(name="cookie", description="cookie commands")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot:
            return
        if message.reference is None:
            return
        if not isinstance(message.guild, discord.Guild):
            return

        cfg = await GuildConfig.load(self.bot.db, message.guild.id)
        if not cfg.economy.cookies:
            return

        content = message.content.lower().strip()
        if not any(p.lower() in content for p in cfg.economy.cookies_messages):
            return

        ref = message.reference
        resolved = ref.resolved
        if not isinstance(resolved, discord.Message):
            return

        target = resolved.author
        if target.bot or target.id == message.author.id:
            return

        await add_cookies(self.bot.db, message.guild.id, target.id, 1)

        name = cfg.economy.cookies_name
        symbol = cfg.economy.cookies_symbol
        try:
            await message.add_reaction(symbol if len(symbol) == 1 else "c")
        except discord.HTTPException:
            pass
        _ = name

    @cookie.command(name="check", description="check your cookie balance")
    @app_commands.describe(user="user to check (defaults to yourself)")
    async def check(
        self,
        interaction: discord.Interaction,
        user: discord.Member | None = None,
    ) -> None:
        if interaction.guild is None:
            return
        cfg = await GuildConfig.load(self.bot.db, interaction.guild.id)
        if not cfg.economy.cookies:
            await interaction.response.send_message(
                "cookies are not enabled on this server", ephemeral=True
            )
            return

        target = user or interaction.user
        amount = await get_cookies(self.bot.db, interaction.guild.id, target.id)
        name = cfg.economy.cookies_name
        layout = BaseLayout()
        layout.add_container(
            ui.TextDisplay(
                f"**{target.display_name}** has **{amount}** {name}{'s' if amount != 1 else ''}"
            ),
            accent_color=0xFEE75C,
        )
        await interaction.response.send_message(view=layout, ephemeral=True)

    @cookie.command(
        name="give", description="give a cookie to someone from your own stash"
    )
    @app_commands.describe(user="who to give a cookie to")
    async def give(
        self,
        interaction: discord.Interaction,
        user: discord.Member,
    ) -> None:
        if interaction.guild is None:
            return
        cfg = await GuildConfig.load(self.bot.db, interaction.guild.id)
        if not cfg.economy.cookies:
            await interaction.response.send_message(
                "cookies are not enabled on this server", ephemeral=True
            )
            return
        if user.bot or user.id == interaction.user.id:
            await interaction.response.send_message("invalid target", ephemeral=True)
            return

        remaining, ok = await subtract_cookies(
            self.bot.db, interaction.guild.id, interaction.user.id, 1
        )
        if not ok:
            await interaction.response.send_message(
                f"you don't have any {cfg.economy.cookies_name}s to give",
                ephemeral=True,
            )
            return

        await add_cookies(self.bot.db, interaction.guild.id, user.id, 1)
        name = cfg.economy.cookies_name
        layout = BaseLayout()
        layout.add_container(
            ui.TextDisplay(
                f"gave a {name} to **{user.display_name}** — you have **{remaining}** left"
            ),
            accent_color=0x57F287,
        )
        await interaction.response.send_message(view=layout, ephemeral=True)

    @cookie.command(name="eat", description="eat a cookie")
    @app_commands.describe(amount="how many to eat (default 1)")
    async def eat(
        self,
        interaction: discord.Interaction,
        amount: app_commands.Range[int, 1, 100] = 1,
    ) -> None:
        if interaction.guild is None:
            return
        cfg = await GuildConfig.load(self.bot.db, interaction.guild.id)
        if not cfg.economy.cookies:
            await interaction.response.send_message(
                "cookies are not enabled on this server", ephemeral=True
            )
            return

        remaining, ok = await subtract_cookies(
            self.bot.db, interaction.guild.id, interaction.user.id, amount
        )
        name = cfg.economy.cookies_name
        if not ok:
            await interaction.response.send_message(
                f"you don't have enough {name}s", ephemeral=True
            )
            return

        layout = BaseLayout()
        layout.add_container(
            ui.TextDisplay(
                f"you ate **{amount}** {name}{'s' if amount != 1 else ''} — **{remaining}** remaining"
            ),
            accent_color=0xFEE75C,
        )
        await interaction.response.send_message(view=layout, ephemeral=True)

    @cookie.command(name="sell", description="sell cookies for currency")
    @app_commands.describe(amount="how many to sell (default: all)")
    async def sell(
        self,
        interaction: discord.Interaction,
        amount: app_commands.Range[int, 1, 10000] | None = None,
    ) -> None:
        if interaction.guild is None:
            return
        cfg = await GuildConfig.load(self.bot.db, interaction.guild.id)
        if not cfg.economy.cookies:
            await interaction.response.send_message(
                "cookies are not enabled on this server", ephemeral=True
            )
            return
        if cfg.economy.cookies_value is None:
            await interaction.response.send_message(
                f"{cfg.economy.cookies_name}s cannot be sold on this server",
                ephemeral=True,
            )
            return
        if not cfg.economy.enabled:
            await interaction.response.send_message(
                "economy is not enabled on this server", ephemeral=True
            )
            return

        current = await get_cookies(
            self.bot.db, interaction.guild.id, interaction.user.id
        )
        sell_amount = amount if amount is not None else current
        if sell_amount == 0 or current == 0:
            await interaction.response.send_message(
                f"you have no {cfg.economy.cookies_name}s to sell", ephemeral=True
            )
            return

        remaining, ok = await subtract_cookies(
            self.bot.db, interaction.guild.id, interaction.user.id, sell_amount
        )
        if not ok:
            await interaction.response.send_message(
                f"you only have **{current}** {cfg.economy.cookies_name}s",
                ephemeral=True,
            )
            return

        earned = sell_amount * cfg.economy.cookies_value
        new_balance = await add_balance(
            self.bot.db, interaction.guild.id, interaction.user.id, earned
        )
        name = cfg.economy.cookies_name
        sym = cfg.economy.currency_symbol
        layout = BaseLayout()
        layout.add_container(
            ui.TextDisplay(
                f"sold **{sell_amount}** {name}{'s' if sell_amount != 1 else ''} for **{sym}{earned:,}**"
                f"\nnew balance: **{sym}{new_balance:,}**"
            ),
            accent_color=0x57F287,
        )
        await interaction.response.send_message(view=layout, ephemeral=True)


async def setup(bot: "Bot") -> None:
    await bot.add_cog(CookiesCog(bot))
