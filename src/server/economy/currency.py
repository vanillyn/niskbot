from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import discord
from discord import app_commands, ui
from discord.ext import commands

from src.data.config import EconomyConfig, GuildConfig
from src.data.economy import (
    ShopItem,
    add_balance,
    delete_shop_item,
    get_balance,
    get_shop_item,
    get_shop_items,
    set_balance,
    subtract_balance,
    upsert_shop_item,
)
from src.server.economy.util import can_manage, fmt
from src.utils.ui import BaseLayout

if TYPE_CHECKING:
    from src.bot import Bot


class _DropView(BaseLayout):
    def __init__(
        self,
        bot: "Bot",
        guild_id: int,
        amount: int,
        cfg: EconomyConfig,
    ) -> None:
        super().__init__(timeout=60.0)
        self._bot = bot
        self._guild_id = guild_id
        self._amount = amount
        self._cfg = cfg
        self._claimed = False
        self._msg: discord.Message | None = None
        self._render()

    def _render(self) -> None:
        self.add_container(
            ui.TextDisplay(
                f"a drop of **{fmt(self._amount, self._cfg)}** appeared — click to claim!"
            ),
            accent_color=0x57F287,
        )
        self.add_sep()
        self.add_item(ui.ActionRow(_ClaimBtn(self)))

    async def on_timeout(self) -> None:
        if self._claimed or self._msg is None:
            return
        expired = BaseLayout()
        expired.add_container(
            ui.TextDisplay(
                f"a drop of **{fmt(self._amount, self._cfg)}** expired unclaimed"
            ),
            accent_color=0x99AAB5,
        )
        try:
            await self._msg.edit(view=expired)
        except discord.HTTPException:
            pass


class _ClaimBtn(ui.Button["_DropView"]):
    def __init__(self, parent: "_DropView") -> None:
        super().__init__(
            label="claim", style=discord.ButtonStyle.success, custom_id="drop:claim"
        )
        self._p = parent

    async def callback(self, interaction: discord.Interaction) -> None:
        if self._p._claimed:
            await interaction.response.send_message("already claimed", ephemeral=True)
            return
        if interaction.guild is None:
            return
        self._p._claimed = True
        self._p.stop()

        new_balance = await add_balance(
            self._p._bot.db,
            interaction.guild.id,
            interaction.user.id,
            self._p._amount,
        )
        result = BaseLayout()
        result.add_container(
            ui.TextDisplay(
                f"{interaction.user.mention} claimed **{fmt(self._p._amount, self._p._cfg)}**!"
                f"\ntheir balance: **{fmt(new_balance, self._p._cfg)}**"
            ),
            accent_color=0x57F287,
        )
        await interaction.response.edit_message(view=result)


class _ShopView(BaseLayout):
    def __init__(
        self,
        bot: "Bot",
        guild: discord.Guild,
        member: discord.Member,
        items: list[ShopItem],
        balance: int,
        cfg: EconomyConfig,
    ) -> None:
        super().__init__(timeout=120.0)
        self._bot = bot
        self._guild = guild
        self._member = member
        self._items = items
        self._balance = balance
        self._cfg = cfg
        self._render()

    def _render(self) -> None:
        lines = [
            f"## {self._cfg.currency_name} shop",
            f"your balance: **{fmt(self._balance, self._cfg)}**",
            "",
        ]
        if not self._items:
            lines.append("no items available")
        else:
            for item in self._items:
                role_notes: list[str] = []
                if item.role_add:
                    role_notes.append(f"grants <@&{item.role_add}>")
                if item.role_remove:
                    role_notes.append(f"removes <@&{item.role_remove}>")
                note = f" ({', '.join(role_notes)})" if role_notes else ""
                lines.append(f"**{item.name}** — {fmt(item.price, self._cfg)}{note}")
                if item.description:
                    lines.append(f"  {item.description}")
        self.add_container(ui.TextDisplay("\n".join(lines)), accent_color=0x5865F2)

        if self._items:
            self.add_sep()
            options = [
                discord.SelectOption(
                    label=item.name,
                    description=f"{fmt(item.price, self._cfg)} — {item.description}"[
                        :100
                    ]
                    if item.description
                    else fmt(item.price, self._cfg),
                    value=item.name,
                )
                for item in self._items
            ]
            select: ui.Select["_ShopView"] = ui.Select(
                placeholder="select an item to buy",
                options=options,
                custom_id="shop:buy",
            )
            select.callback = self._on_buy  # type: ignore[method-assign]
            self.add_item(ui.ActionRow(select))

        from src.member.util import _is_admin

        if _is_admin(self._member):
            btn: ui.Button["_ShopView"] = ui.Button(
                label="manage items",
                style=discord.ButtonStyle.secondary,
                custom_id="shop:manage",
            )
            btn.callback = self._on_manage  # type: ignore[method-assign]
            self.add_item(ui.ActionRow(btn))

    async def _on_buy(self, interaction: discord.Interaction) -> None:
        select = discord.utils.get(
            [
                i
                for row in self.children
                if isinstance(row, ui.ActionRow)
                for i in row.children
            ],
            custom_id="shop:buy",
        )
        if not isinstance(select, ui.Select):
            return
        item_name = select.values[0]
        item = await get_shop_item(self._bot.db, self._guild.id, item_name)
        if item is None:
            await interaction.response.send_message("item not found", ephemeral=True)
            return

        balance = await get_balance(self._bot.db, self._guild.id, interaction.user.id)
        if balance < item.price:
            await interaction.response.send_message(
                f"not enough {self._cfg.currency_name} — you have **{fmt(balance, self._cfg)}**",
                ephemeral=True,
            )
            return

        new_balance, ok = await subtract_balance(
            self._bot.db, self._guild.id, interaction.user.id, item.price
        )
        if not ok:
            await interaction.response.send_message(
                "purchase failed — balance changed", ephemeral=True
            )
            return

        member = self._guild.get_member(interaction.user.id)
        role_results: list[str] = []
        if member is not None:
            if item.role_add:
                role = self._guild.get_role(item.role_add)
                if role is not None:
                    try:
                        await member.add_roles(
                            role, reason=f"shop purchase: {item.name}"
                        )
                        role_results.append(f"added **{role.name}**")
                    except discord.HTTPException:
                        pass
            if item.role_remove:
                role = self._guild.get_role(item.role_remove)
                if role is not None:
                    try:
                        await member.remove_roles(
                            role, reason=f"shop purchase: {item.name}"
                        )
                        role_results.append(f"removed **{role.name}**")
                    except discord.HTTPException:
                        pass

        lines = [
            f"purchased **{item.name}** for {fmt(item.price, self._cfg)}",
            f"new balance: **{fmt(new_balance, self._cfg)}**",
        ]
        if role_results:
            lines.extend(role_results)

        layout = BaseLayout()
        layout.add_container(ui.TextDisplay("\n".join(lines)), accent_color=0x57F287)
        await interaction.response.send_message(view=layout, ephemeral=True)

    async def _on_manage(self, interaction: discord.Interaction) -> None:
        from src.member.util import _is_admin

        if not isinstance(interaction.user, discord.Member) or not _is_admin(
            interaction.user
        ):
            await interaction.response.send_message(
                "missing permissions", ephemeral=True
            )
            return
        items = await get_shop_items(self._bot.db, self._guild.id)
        view = _ShopManageView(self._bot, self._guild, items, self._cfg)
        await interaction.response.send_message(view=view, ephemeral=True)


class _ShopManageView(BaseLayout):
    def __init__(
        self,
        bot: "Bot",
        guild: discord.Guild,
        items: list[ShopItem],
        cfg: EconomyConfig,
    ) -> None:
        super().__init__(timeout=300.0)
        self._bot = bot
        self._guild = guild
        self._items = items
        self._cfg = cfg
        self._render()

    def _render(self) -> None:
        lines = ["**shop management**", ""]
        if not self._items:
            lines.append("no items yet")
        else:
            for item in self._items:
                lines.append(f"**{item.name}** — {fmt(item.price, self._cfg)}")
                if item.description:
                    lines.append(f"  {item.description}")
                if item.role_add:
                    lines.append(f"  grants <@&{item.role_add}>")
                if item.role_remove:
                    lines.append(f"  removes <@&{item.role_remove}>")
        self.add_container(ui.TextDisplay("\n".join(lines)))
        self.add_sep()

        add_btn: ui.Button["_ShopManageView"] = ui.Button(
            label="add item", style=discord.ButtonStyle.primary, custom_id="shop:add"
        )
        add_btn.callback = self._on_add  # type: ignore[method-assign]
        row: ui.ActionRow["_ShopManageView"] = ui.ActionRow(add_btn)

        if self._items:
            remove_btn: ui.Button["_ShopManageView"] = ui.Button(
                label="remove item",
                style=discord.ButtonStyle.danger,
                custom_id="shop:remove",
            )
            remove_btn.callback = self._on_remove  # type: ignore[method-assign]
            row.add_item(remove_btn)

        self.add_item(row)

    async def _on_add(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(_AddItemModal(self))

    async def _on_remove(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(_RemoveItemModal(self))

    async def _refresh(self, interaction: discord.Interaction) -> None:
        self._items = await get_shop_items(self._bot.db, self._guild.id)
        new_view = _ShopManageView(self._bot, self._guild, self._items, self._cfg)
        if interaction.type == discord.InteractionType.modal_submit:
            await interaction.response.defer()
            try:
                await interaction.edit_original_response(view=new_view)
            except discord.HTTPException:
                pass
        else:
            await interaction.response.edit_message(view=new_view)


class _AddItemModal(ui.Modal, title="add shop item"):
    name_field: ui.TextInput["_AddItemModal"] = ui.TextInput(
        label="item name", custom_id="name", max_length=50, required=True
    )
    desc_field: ui.TextInput["_AddItemModal"] = ui.TextInput(
        label="description",
        custom_id="desc",
        max_length=200,
        required=False,
        style=discord.TextStyle.paragraph,
    )
    price_field: ui.TextInput["_AddItemModal"] = ui.TextInput(
        label="price", custom_id="price", max_length=10, required=True
    )
    role_add_field: ui.TextInput["_AddItemModal"] = ui.TextInput(
        label="role id to add (optional)",
        custom_id="role_add",
        max_length=20,
        required=False,
    )
    role_remove_field: ui.TextInput["_AddItemModal"] = ui.TextInput(
        label="role id to remove (optional)",
        custom_id="role_remove",
        max_length=20,
        required=False,
    )

    def __init__(self, parent: "_ShopManageView") -> None:
        super().__init__()
        self._p = parent

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            price = int(self.price_field.value.strip())
        except ValueError:
            await interaction.response.send_message("invalid price", ephemeral=True)
            return

        role_add: int | None = None
        role_remove: int | None = None
        raw_add = self.role_add_field.value.strip()
        raw_remove = self.role_remove_field.value.strip()
        if raw_add:
            try:
                role_add = int(raw_add)
            except ValueError:
                await interaction.response.send_message(
                    "invalid role id for role_add", ephemeral=True
                )
                return
        if raw_remove:
            try:
                role_remove = int(raw_remove)
            except ValueError:
                await interaction.response.send_message(
                    "invalid role id for role_remove", ephemeral=True
                )
                return

        await upsert_shop_item(
            self._p._bot.db,
            self._p._guild.id,
            self.name_field.value.strip(),
            self.desc_field.value.strip() if self.desc_field.value else "",
            price,
            role_add,
            role_remove,
        )
        await self._p._refresh(interaction)

    async def on_error(
        self, interaction: discord.Interaction, error: Exception
    ) -> None:
        if not interaction.response.is_done():
            await interaction.response.send_message(
                "something went wrong", ephemeral=True
            )
        raise error


class _RemoveItemModal(ui.Modal, title="remove shop item"):
    name_field: ui.TextInput["_RemoveItemModal"] = ui.TextInput(
        label="item name to remove", custom_id="name", max_length=50, required=True
    )

    def __init__(self, parent: "_ShopManageView") -> None:
        super().__init__()
        self._p = parent

    async def on_submit(self, interaction: discord.Interaction) -> None:
        removed = await delete_shop_item(
            self._p._bot.db, self._p._guild.id, self.name_field.value.strip()
        )
        if not removed:
            await interaction.response.send_message("item not found", ephemeral=True)
            return
        await self._p._refresh(interaction)

    async def on_error(
        self, interaction: discord.Interaction, error: Exception
    ) -> None:
        if not interaction.response.is_done():
            await interaction.response.send_message(
                "something went wrong", ephemeral=True
            )
        raise error


class EconomyCog(commands.Cog, name="economy"):
    def __init__(self, bot: "Bot") -> None:
        self.bot = bot

    economy = app_commands.Group(name="economy", description="economy commands")

    @economy.command(name="check", description="check a user's balance")
    @app_commands.describe(user="user to check (defaults to yourself)")
    async def check(
        self,
        interaction: discord.Interaction,
        user: discord.Member | None = None,
    ) -> None:
        if interaction.guild is None:
            return
        cfg = await GuildConfig.load(self.bot.db, interaction.guild.id)
        if not cfg.economy.enabled:
            await interaction.response.send_message(
                "economy is not enabled on this server", ephemeral=True
            )
            return
        target = user or interaction.user
        balance = await get_balance(self.bot.db, interaction.guild.id, target.id)
        layout = BaseLayout()
        layout.add_container(
            ui.TextDisplay(
                f"**{target.display_name}**'s balance: **{fmt(balance, cfg.economy)}**"
            ),
            accent_color=0x5865F2,
        )
        await interaction.response.send_message(view=layout, ephemeral=True)

    @economy.command(name="edit", description="set a user's balance exactly (admin)")
    @app_commands.describe(user="target user", amount="new balance amount")
    async def edit(
        self,
        interaction: discord.Interaction,
        user: discord.Member,
        amount: app_commands.Range[int, 0, 10_000_000],
    ) -> None:
        if interaction.guild is None or not isinstance(
            interaction.user, discord.Member
        ):
            return
        if not await can_manage(self.bot.db, interaction.user):
            await interaction.response.send_message(
                "missing permissions", ephemeral=True
            )
            return
        cfg = await GuildConfig.load(self.bot.db, interaction.guild.id)
        await set_balance(self.bot.db, interaction.guild.id, user.id, amount)
        layout = BaseLayout()
        layout.add_container(
            ui.TextDisplay(
                f"set **{user.display_name}**'s balance to **{fmt(amount, cfg.economy)}**"
            ),
            accent_color=0x5865F2,
        )
        await interaction.response.send_message(view=layout, ephemeral=True)

    @economy.command(name="pay", description="add currency to a user's balance (admin)")
    @app_commands.describe(user="target user", amount="amount to add")
    async def pay(
        self,
        interaction: discord.Interaction,
        user: discord.Member,
        amount: app_commands.Range[int, 1, 10_000_000],
    ) -> None:
        if interaction.guild is None or not isinstance(
            interaction.user, discord.Member
        ):
            return
        if not await can_manage(self.bot.db, interaction.user):
            await interaction.response.send_message(
                "missing permissions", ephemeral=True
            )
            return
        cfg = await GuildConfig.load(self.bot.db, interaction.guild.id)
        new_balance = await add_balance(
            self.bot.db, interaction.guild.id, user.id, amount
        )
        layout = BaseLayout()
        layout.add_container(
            ui.TextDisplay(
                f"gave **{fmt(amount, cfg.economy)}** to **{user.display_name}**"
                f"\ntheir balance: **{fmt(new_balance, cfg.economy)}**"
            ),
            accent_color=0x57F287,
        )
        await interaction.response.send_message(view=layout, ephemeral=True)

    @economy.command(
        name="take", description="remove currency from a user's balance (admin)"
    )
    @app_commands.describe(user="target user", amount="amount to remove")
    async def take(
        self,
        interaction: discord.Interaction,
        user: discord.Member,
        amount: app_commands.Range[int, 1, 10_000_000],
    ) -> None:
        if interaction.guild is None or not isinstance(
            interaction.user, discord.Member
        ):
            return
        if not await can_manage(self.bot.db, interaction.user):
            await interaction.response.send_message(
                "missing permissions", ephemeral=True
            )
            return
        cfg = await GuildConfig.load(self.bot.db, interaction.guild.id)
        new_balance, ok = await subtract_balance(
            self.bot.db, interaction.guild.id, user.id, amount
        )
        note = "" if ok else " (clamped to 0)"
        layout = BaseLayout()
        layout.add_container(
            ui.TextDisplay(
                f"took **{fmt(amount, cfg.economy)}** from **{user.display_name}**{note}"
                f"\ntheir balance: **{fmt(new_balance, cfg.economy)}**"
            ),
            accent_color=0xED4245,
        )
        await interaction.response.send_message(view=layout, ephemeral=True)

    @economy.command(
        name="drop", description="drop currency for anyone to claim (admin)"
    )
    @app_commands.describe(
        amount="amount to drop", channel="channel to drop in (default: current)"
    )
    async def drop(
        self,
        interaction: discord.Interaction,
        amount: app_commands.Range[int, 1, 1_000_000],
        channel: discord.TextChannel | None = None,
    ) -> None:
        if interaction.guild is None or not isinstance(
            interaction.user, discord.Member
        ):
            return
        if not await can_manage(self.bot.db, interaction.user):
            await interaction.response.send_message(
                "missing permissions", ephemeral=True
            )
            return
        cfg = await GuildConfig.load(self.bot.db, interaction.guild.id)
        if not cfg.economy.enabled:
            await interaction.response.send_message(
                "economy is not enabled", ephemeral=True
            )
            return

        target_channel = channel
        if target_channel is None:
            if not isinstance(interaction.channel, discord.TextChannel):
                await interaction.response.send_message(
                    "run in a text channel or specify one", ephemeral=True
                )
                return
            target_channel = interaction.channel

        view = _DropView(self.bot, interaction.guild.id, amount, cfg.economy)
        msg = await target_channel.send(view=view)
        view._msg = msg
        await interaction.response.send_message(
            f"drop sent to {target_channel.mention}", ephemeral=True
        )

    @economy.command(name="shop", description="browse and buy from the shop")
    async def shop(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None or not isinstance(
            interaction.user, discord.Member
        ):
            return
        cfg = await GuildConfig.load(self.bot.db, interaction.guild.id)
        if not cfg.economy.enabled:
            await interaction.response.send_message(
                "economy is not enabled on this server", ephemeral=True
            )
            return
        items = await get_shop_items(self.bot.db, interaction.guild.id)
        balance = await get_balance(
            self.bot.db, interaction.guild.id, interaction.user.id
        )
        view = _ShopView(
            self.bot,
            interaction.guild,
            interaction.user,
            items,
            balance,
            cfg.economy,
        )
        await interaction.response.send_message(view=view, ephemeral=True)


async def setup(bot: "Bot") -> None:
    await bot.add_cog(EconomyCog(bot))
